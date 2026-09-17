"""The extractor that always works: text out of the PDF, then patterns.

It is the fallback, so it has no dependency on any key, any network and anyone's uptime. It reads
French and English forwarder invoices, which is what the customers get: « Facture n° », « THC »,
« surestaries », amounts as 1 234,56 and as 1,234.56.

It is not clever, and it does not pretend to be: what it cannot pin down comes back with a low
confidence and no cost type, which puts the line in front of a person — where it was going anyway.
"""

from __future__ import annotations

import io
import logging
import re
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.domain.invoices.ports import (
    ExtractedLine,
    ExtractionContext,
    ExtractionFailed,
    ExtractionInput,
    FreightInvoice,
)
from app.domain.models import CostType

logger = logging.getLogger(__name__)

CONTAINER_RE = re.compile(r"\b([A-Z]{4})[ -]?(\d{7})\b")
BL_RE = re.compile(r"\b(?:B/?L|BILL OF LADING|CONNAISSEMENT)[\s:n°#]*([A-Z0-9]{6,20})\b", re.IGNORECASE)
PO_RE = re.compile(r"\b(?:PO|P\.O\.|COMMANDE)[\s:n°#-]*([A-Z0-9][A-Z0-9-]{3,20})\b", re.IGNORECASE)
INVOICE_NO_RE = re.compile(
    r"(?:FACTURE|INVOICE)\s*(?:N[°ºo]|NO|NUMBER|#)?\s*[:.]?\s*([A-Z0-9][A-Z0-9/-]{3,24})", re.IGNORECASE
)
# French invoices group thousands with a space, often a non-breaking one.
DATE_RE = re.compile(r"\b(\d{2})[/.-](\d{2})[/.-](\d{4})\b|\b(\d{4})-(\d{2})-(\d{2})\b")
AMOUNT_RE = re.compile(r"(?<![\d.,])\d{1,3}(?:[\u00a0 .,]\d{3})*(?:[.,]\d{1,2})?(?![\d])")
CURRENCY_RE = re.compile(r"\b(EUR|USD|GBP|CNY|CHF)\b|([€$£])")
CURRENCY_SYMBOLS = {"€": "EUR", "$": "USD", "£": "GBP"}
#: What an invoice puts after the amount in the last column, and nothing else.
TRAILING_NOISE_RE = re.compile(r"[\s]*(?:EUR|USD|GBP|CNY|CHF|€|\$|£|HT|TTC|TVAC|\*+)?[\s.]*$", re.IGNORECASE)

#: The minus signs a PDF actually carries: the keyboard hyphen, and the typographic minus that most
#: invoice fonts print instead of it.
MINUS_SIGNS = ("-", "\u2212")
#: A refund, in the words French and English invoices head it with. « Avoir » is also an ordinary
#: verb, so it only counts in the header block, where a document states what it is.
CREDIT_NOTE_RE = re.compile(r"\bAVOIRS?\b|\bNOTE\s+DE\s+CR[EÉ]DIT\b|\bCREDIT\s+NOTE\b", re.IGNORECASE)
#: How far down the page a document is still introducing itself.
HEADER_LINES = 12

TOTAL_WORDS = ("TOTAL TTC", "TOTAL À PAYER", "TOTAL A PAYER", "MONTANT TOTAL", "TOTAL DUE", "TOTAL")
VAT_WORDS = ("TVA", "VAT", "T.V.A")
#: « TVA FR12812345678 » is the supplier's registration number, not an amount of tax. Same for a
#: line that only states the taxable base.
VAT_NUMBER_RE = re.compile(r"\bTVA\s*[A-Z]{2}\s*\d{6,}|\bVAT\s*(?:NO|NUMBER|N[°º])", re.IGNORECASE)
SUBTOTAL_WORDS = ("TOTAL HT", "SOUS-TOTAL", "SUBTOTAL", "TOTAL EXCL")

#: Words that name a charge, in the two languages the customers' invoices come in.
COST_KEYWORDS: tuple[tuple[str, CostType], ...] = (
    ("THC", CostType.THC),
    ("TERMINAL HANDLING", CostType.THC),
    ("MANUTENTION", CostType.THC),
    ("SURESTARIE", CostType.DEMURRAGE),
    ("DEMURRAGE", CostType.DEMURRAGE),
    ("DETENTION", CostType.DETENTION),
    ("DÉTENTION", CostType.DETENTION),
    ("CAMIONNAGE", CostType.DRAYAGE),
    ("DRAYAGE", CostType.DRAYAGE),
    ("LIVRAISON", CostType.DRAYAGE),
    ("TRUCKING", CostType.DRAYAGE),
    # Swapping a box between two trucks is a haulage operation, billed by the haulier.
    ("ECHANGE DE CONTENEUR", CostType.DRAYAGE),
    ("ÉCHANGE DE CONTENEUR", CostType.DRAYAGE),
    ("FRET AERIEN", CostType.AIR_FREIGHT),
    ("AIR FREIGHT", CostType.AIR_FREIGHT),
    ("FRET MARITIME", CostType.OCEAN_FREIGHT),
    ("OCEAN FREIGHT", CostType.OCEAN_FREIGHT),
    ("SEA FREIGHT", CostType.OCEAN_FREIGHT),
    ("FRET", CostType.OCEAN_FREIGHT),
    ("FREIGHT", CostType.OCEAN_FREIGHT),
    ("ASSURANCE", CostType.INSURANCE),
    ("INSURANCE", CostType.INSURANCE),
    ("DROITS DE DOUANE", CostType.CUSTOMS_DUTY),
    ("CUSTOMS DUTY", CostType.CUSTOMS_DUTY),
    ("DEDOUANEMENT", CostType.CUSTOMS_BROKERAGE),
    ("DÉDOUANEMENT", CostType.CUSTOMS_BROKERAGE),
    ("CUSTOMS CLEARANCE", CostType.CUSTOMS_BROKERAGE),
    ("HONORAIRES DOUANE", CostType.CUSTOMS_BROKERAGE),
    # The customs agent's own fee, as his invoice names it — « honoraires d'agréé en douane », HAD.
    ("HONORAIRES D'AGREE", CostType.CUSTOMS_BROKERAGE),
    ("HONORAIRES D'AGRÉÉ", CostType.CUSTOMS_BROKERAGE),
    ("FRAIS DE DOSSIER", CostType.BL_FEE),
    ("BL FEE", CostType.BL_FEE),
    ("B/L", CostType.BL_FEE),
    ("BILL OF LADING", CostType.BL_FEE),
    ("CONNAISSEMENT", CostType.BL_FEE),
    # Releasing the bill of lading is what the « frais de release » on a forwarder's invoice buys.
    ("RELEASE", CostType.BL_FEE),
    ("ENTREPOSAGE", CostType.WAREHOUSING),
    # What a terminal or a forwarder calls storage in French: « entreposage » is a bonded warehouse,
    # « magasinage » and « stationnement » are the box sitting on the terminal, which is the charge.
    ("MAGASINAGE", CostType.WAREHOUSING),
    ("STATIONNEMENT", CostType.WAREHOUSING),
    ("DEPOTAGE", CostType.WAREHOUSING),
    ("DÉPOTAGE", CostType.WAREHOUSING),
    ("STORAGE", CostType.WAREHOUSING),
    ("WAREHOUS", CostType.WAREHOUSING),
    ("INSPECTION", CostType.INSPECTION),
    # Customs pulling the box for a look, by scanner or by hand: billed as an inspection.
    ("VISITE DOUANE", CostType.INSPECTION),
    ("VISITE DOUANIERE", CostType.INSPECTION),
    ("VISITE DOUANIÈRE", CostType.INSPECTION),
    ("SCANNER", CostType.INSPECTION),
    ("SCANNING", CostType.INSPECTION),
    ("FRAIS BANCAIRES", CostType.BANK_FEES),
    ("BANK FEE", CostType.BANK_FEES),
    ("FRAIS ORIGINE", CostType.ORIGIN_CHARGES),
    ("ORIGIN CHARGE", CostType.ORIGIN_CHARGES),
)

#: The charges that ocean invoices name by their initials, which cannot be looked for as substrings:
#: « ENS » sits inside « DÉPENSES », « HAD » inside a dozen words. They are matched as whole words.
#:
#: The surcharges (BAF, CAF, LSS, PSS, ISPS) are the freight rate cut into pieces by the carrier's
#: tariff — one voyage, billed in five lines — so they land on OCEAN_FREIGHT, where they are
#: allocated exactly as the base freight is; the wording keeps the detail for whoever reads it.
COST_ACRONYMS: tuple[tuple[str, CostType], ...] = (
    ("BAF", CostType.OCEAN_FREIGHT),
    ("CAF", CostType.OCEAN_FREIGHT),
    ("LSS", CostType.OCEAN_FREIGHT),
    ("PSS", CostType.OCEAN_FREIGHT),
    ("ISPS", CostType.OCEAN_FREIGHT),
    ("ENS", CostType.CUSTOMS_BROKERAGE),
    ("T1", CostType.CUSTOMS_BROKERAGE),
    ("HAD", CostType.CUSTOMS_BROKERAGE),
)
ACRONYM_RE = re.compile(rf"(?<![A-Z0-9])({'|'.join(k for k, _ in COST_ACRONYMS)})(?![A-Z0-9])")
#: « Valeur CAF » is the customs value of the goods — the same three letters as the currency
#: surcharge, on a line that is not a charge at all. Reading it as freight would invent thousands.
NOT_A_CHARGE_RE = re.compile(r"VALEUR\s+CAF|CAF\s+VALUE")


def text_of(document: ExtractionInput) -> str:
    if document.content_type != "application/pdf":
        raise ExtractionFailed(
            "Only PDF invoices can be read without a vision model; this one is an image. "
            "Enter its costs by hand, or configure the LLM extractor.",
            code="NO_TEXT_LAYER",
        )
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(document.content))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise ExtractionFailed(f"This PDF could not be read: {exc}", code="UNREADABLE_PDF") from exc
    text = "\n".join(pages).strip()
    if not text:
        raise ExtractionFailed(
            "This PDF has no text layer — it is probably a scan. Enter its costs by hand, or "
            "configure the LLM extractor.",
            code="NO_TEXT_LAYER",
        )
    return text


def parse_amount(raw: str) -> Decimal | None:
    """Read an amount written either way round: 1 234,56 and 1,234.56 are the same money.

    The rule is the one a person uses: whichever of `.` or `,` comes last is the decimal separator,
    and a lone separator followed by exactly three digits is a thousands group.
    """
    text = raw.strip().replace("\u00a0", "").replace(" ", "")
    if not text or not any(ch.isdigit() for ch in text):
        return None
    last_dot, last_comma = text.rfind("."), text.rfind(",")
    if last_dot >= 0 and last_comma >= 0:
        decimal_at = max(last_dot, last_comma)
        integer = re.sub(r"[.,]", "", text[:decimal_at])
        fraction = text[decimal_at + 1 :]
    elif last_dot >= 0 or last_comma >= 0:
        decimal_at = max(last_dot, last_comma)
        integer, fraction = text[:decimal_at].replace(".", "").replace(",", ""), text[decimal_at + 1 :]
        if len(fraction) == 3:  # 3 000 or 4,200: a thousands group, not centimes
            integer, fraction = integer + fraction, ""
    else:
        integer, fraction = text, ""
    if not integer.isdigit() or (fraction and not fraction.isdigit()):
        return None
    try:
        return Decimal(f"{integer}.{(fraction or '00')[:2]:0<2}")
    except InvalidOperation:  # pragma: no cover
        return None


def is_negative(text: str, start: int, end: int) -> bool:
    """Whether the amount at `text[start:end]` is written as a negative one.

    Four notations reach us from real documents and all four mean the same refund: a minus glued to
    the figure, a minus loose in front of it, the typographic minus the PDF font carries instead of
    the hyphen, a minus printed after the figure, and the accountant's parentheses. Reading any of
    them as a charge turns a credit note into money owed, twice over — once as a refund never
    received, once as a cost never incurred.
    """
    before = text[:start].rstrip(" \u00a0")
    after = text[end:].lstrip(" \u00a0")
    if before.endswith(MINUS_SIGNS) or after.startswith(MINUS_SIGNS):
        return True
    return before.endswith("(") and after.startswith(")")


def trailing_amount(line: str) -> Decimal | None:
    """The rightmost number, signed, but only when the line actually *ends* on it.

    An invoice table puts the money in the last column. A header sentence that happens to name a
    charge — « Dossier · B/L MEDUSH2604417 · Conteneur MSCU1234567 (40' HC) · Navire… » — has its
    numbers in the middle, and reading 40 as a bill-of-lading fee is exactly the kind of quiet
    nonsense a review is supposed to be spared. What a figure may still be followed by is its own
    sign: a trailing minus, or the parenthesis that closes an accounting negative.
    """
    stripped = TRAILING_NOISE_RE.sub("", line.rstrip())
    matches = list(AMOUNT_RE.finditer(stripped))
    if not matches:
        return None
    last = matches[-1]
    negative = is_negative(stripped, last.start(), last.end())
    rest = stripped[last.end() :].strip(" \u00a0")
    if rest not in ("", *MINUS_SIGNS) and not (negative and rest == ")"):
        return None
    value = parse_amount(last.group(0))
    if value is None:
        return None
    return -value if negative else value


def describe(line: str) -> str:
    """The words of a table row, without the numeric columns that follow them.

    « Fret maritime Shanghai / Le Havre (Ocean freight) 1 2 450,00 2 450,00 » is a description and
    three columns — quantity, unit price, amount — and showing the columns back to whoever is
    reviewing the charge is showing them the table's plumbing. Only a run of numbers that reaches
    the end of the line is cut, so a quantity inside the wording (« Surestaries 5 jours ») stays.
    """
    tail_free = TRAILING_NOISE_RE.sub("", line)  # the € or the EUR the last column ends with
    matches = list(AMOUNT_RE.finditer(tail_free))
    if not matches:
        return line
    cut = len(tail_free)
    for match in reversed(matches):
        if tail_free[match.end() : cut].strip():
            break  # something other than whitespace between the columns: the wording starts here
        cut = match.start()
    return _without_separators(tail_free[:cut]) or line


#: What an invoice leaves between the wording and its columns, once the numbers are gone.
COLUMN_SEPARATORS = " \t\u00b7\u2013\u2014-\u2212:*"


def _without_separators(head: str) -> str:
    """Trim what joined the wording to the columns, and nothing that belongs to a word."""
    head = head.rstrip(COLUMN_SEPARATORS)
    # « Surestaries 5 jours x 80,00 » leaves a dangling multiplication sign. Bordeaux keeps its
    # last letter: the sign stands alone, the letter does not.
    while head[-1:] in ("x", "\u00d7") and (len(head) == 1 or head[-2:-1].isspace()):
        head = head[:-1].rstrip(COLUMN_SEPARATORS)
    return head


def find_currency(text: str) -> str | None:
    match = CURRENCY_RE.search(text)
    if not match:
        return None
    return match.group(1) or CURRENCY_SYMBOLS.get(match.group(2) or "")


def currencies_in(text: str) -> list[str]:
    """Every currency the document names, in the order it names them, without repeats."""
    seen: list[str] = []
    for match in CURRENCY_RE.finditer(text):
        code = match.group(1) or CURRENCY_SYMBOLS.get(match.group(2) or "")
        if code and code not in seen:
            seen.append(code)
    return seen


def document_currency(lines: list[str], upper_lines: list[str]) -> tuple[str | None, list[str]]:
    """What the invoice is denominated in, and every currency it mentions.

    The one thing that must not decide is the first currency word on the page: a forwarder prints
    the day's USD/EUR rate in its header and its dollar IBAN in its footer, and a EUR invoice read
    as USD is converted twice — around 8 % of landed cost, silently, with a perfectly valid rate.

    So the totals line comes first: that is where a document commits to what it wants to be paid in.
    Failing that, the currency most of the charge lines carry — a majority of rows beats a sentence.
    """
    named = currencies_in("\n".join(lines))
    totals = [
        raw
        for raw, upper in zip(lines, upper_lines, strict=True)
        if any(word in upper for word in (*TOTAL_WORDS, *SUBTOTAL_WORDS))
    ]
    for raw in reversed(totals):  # invoices repeat their totals; the last one is the one to pay
        stated = find_currency(raw)
        if stated:
            return stated, named
    counted = Counter(
        code for raw in lines if trailing_amount(raw) is not None and (code := find_currency(raw)) is not None
    )
    if not counted:
        return None, named
    return counted.most_common(1)[0][0], named


def find_date(text: str) -> date | None:
    for match in DATE_RE.finditer(text):
        try:
            if match.group(1):
                return datetime(  # noqa: DTZ001 - an invoice date has no time zone
                    int(match.group(3)), int(match.group(2)), int(match.group(1))
                ).date()
            return datetime(  # noqa: DTZ001
                int(match.group(4)), int(match.group(5)), int(match.group(6))
            ).date()
        except ValueError:
            continue  # 32/13/2026 and friends
    return None


def cost_type_of(line: str) -> CostType | None:
    upper = line.upper()
    for keyword, cost_type in COST_KEYWORDS:
        if keyword in upper:
            return cost_type
    if NOT_A_CHARGE_RE.search(upper):
        return None
    match = ACRONYM_RE.search(upper)
    if match:
        return dict(COST_ACRONYMS)[match.group(1)]
    return None


def containers_in(text: str) -> list[str]:
    seen: list[str] = []
    for match in CONTAINER_RE.finditer(text.upper()):
        number = f"{match.group(1)}{match.group(2)}"
        if number not in seen:
            seen.append(number)
    return seen


class RegexExtractor:
    name = "regex"

    def extract(self, document: ExtractionInput, context: ExtractionContext) -> FreightInvoice:
        text = text_of(document)
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        upper_lines = [ln.upper() for ln in lines]

        stated_currency, named_currencies = document_currency(lines, upper_lines)
        currency = stated_currency or context.base_currency
        total = self._labelled(lines, upper_lines, TOTAL_WORDS, exclude=SUBTOTAL_WORDS)
        subtotal = self._labelled(lines, upper_lines, SUBTOTAL_WORDS)
        vat = self._vat(lines, upper_lines, total, subtotal)
        invoice_number = None
        if match := INVOICE_NO_RE.search(text):
            invoice_number = match.group(1).strip(" .:")

        charges: list[ExtractedLine] = []
        for raw, upper in zip(lines, upper_lines, strict=True):
            cost_type = cost_type_of(raw)
            if cost_type is None:
                continue
            if any(word in upper for word in (*TOTAL_WORDS, *VAT_WORDS, *SUBTOTAL_WORDS)):
                continue  # a total that happens to name a charge is not a charge
            amount = trailing_amount(raw)
            if amount is None or amount == 0:
                continue  # a charge of nothing is a table rule or a heading, not money
            charges.append(
                ExtractedLine(
                    description=describe(raw),
                    amount=f"{amount:.2f}",
                    currency=find_currency(raw) or currency,
                    cost_type=cost_type,
                    container_number=next(iter(containers_in(raw)), None),
                    confidence=0.6,
                )
            )

        notes: list[str] = []
        if CREDIT_NOTE_RE.search("\n".join(lines[:HEADER_LINES])):
            notes.append("@credit_note|header")
        if len(named_currencies) > 1:
            others = [c for c in named_currencies if c != currency]
            notes.append("|".join(["@currency_guess", currency, *others]))
        if not charges:
            notes.append("No charge line recognised; every amount needs entering by hand.")

        vendor = next((ln for ln in lines[:3] if not ln.upper().startswith(("FACTURE", "INVOICE"))), None)
        return FreightInvoice(
            vendor=vendor,
            invoice_number=invoice_number,
            invoice_date=find_date(text),
            currency=currency,
            total=f"{total:.2f}" if total is not None else None,
            subtotal=f"{subtotal:.2f}" if subtotal is not None else None,
            vat=f"{vat:.2f}" if vat is not None else None,
            lines=charges,
            container_numbers=containers_in(text),
            bl_numbers=[m.group(1) for m in BL_RE.finditer(text)],
            po_numbers=[m.group(1).upper() for m in PO_RE.finditer(text)],
            confidence=0.6 if charges else 0.2,
            notes=notes,
        )

    def _vat(
        self,
        lines: list[str],
        upper_lines: list[str],
        total: Decimal | None,
        subtotal: Decimal | None,
    ) -> Decimal | None:
        """The tax, which is the hardest number on a French invoice to read.

        Arithmetic first: when the invoice states both a total and a subtotal, the tax is their
        difference and no wording can mislead us. Only then fall back to reading a labelled line,
        skipping the ones that carry a registration number rather than an amount.

        The difference has to point the same way as the invoice itself: on a credit note every
        figure is negative, and the tax with them. A gap that points the other way means one of the
        two totals was misread, and a tax invented from it would be worse than none.
        """
        if total is not None and subtotal is not None:
            difference = total - subtotal
            if difference == 0 or (difference < 0) == (total < 0):
                return difference
        candidates = [
            (raw, upper)
            for raw, upper in zip(lines, upper_lines, strict=True)
            if any(word in upper for word in VAT_WORDS) and not VAT_NUMBER_RE.search(raw)
        ]
        if not candidates:
            return None
        return self._labelled([c[0] for c in candidates], [c[1] for c in candidates], VAT_WORDS)

    def _labelled(
        self,
        lines: list[str],
        upper_lines: list[str],
        words: tuple[str, ...],
        exclude: tuple[str, ...] = (),
    ) -> Decimal | None:
        """The amount on the last *row* naming one of these words. Invoices repeat their totals.

        A row ends on its figure; a sentence does not, and a footer naming the word is a sentence.
        « Fret et THC exonérés de TVA (art. 262 II-14° CGI) … IBAN FR76 3000 4000 0500 » is the last
        line of a real invoice that names the tax, and it once made the VAT 76.
        """
        found: Decimal | None = None
        for raw, upper in zip(lines, upper_lines, strict=True):
            if any(word in upper for word in exclude):
                continue
            if any(word in upper for word in words):
                amount = trailing_amount(raw)
                if amount is not None:
                    found = amount
        return found
