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
    ("CAMIONNAGE", CostType.DRAYAGE),
    ("DRAYAGE", CostType.DRAYAGE),
    ("LIVRAISON", CostType.DRAYAGE),
    ("TRUCKING", CostType.DRAYAGE),
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
    ("FRAIS DE DOSSIER", CostType.BL_FEE),
    ("BL FEE", CostType.BL_FEE),
    ("B/L", CostType.BL_FEE),
    ("BILL OF LADING", CostType.BL_FEE),
    ("CONNAISSEMENT", CostType.BL_FEE),
    ("ENTREPOSAGE", CostType.WAREHOUSING),
    ("STORAGE", CostType.WAREHOUSING),
    ("WAREHOUS", CostType.WAREHOUSING),
    ("INSPECTION", CostType.INSPECTION),
    ("FRAIS BANCAIRES", CostType.BANK_FEES),
    ("BANK FEE", CostType.BANK_FEES),
    ("FRAIS ORIGINE", CostType.ORIGIN_CHARGES),
    ("ORIGIN CHARGE", CostType.ORIGIN_CHARGES),
)


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


def last_amount(line: str) -> Decimal | None:
    """The rightmost number on the line: quantities and unit rates come before it."""
    found = [parse_amount(m.group(0)) for m in AMOUNT_RE.finditer(line)]
    values = [v for v in found if v is not None]
    return values[-1] if values else None


def trailing_amount(line: str) -> Decimal | None:
    """The rightmost number, but only when the line actually *ends* on it.

    An invoice table puts the money in the last column. A header sentence that happens to name a
    charge — « Dossier · B/L MEDUSH2604417 · Conteneur MSCU1234567 (40' HC) · Navire… » — has its
    numbers in the middle, and reading 40 as a bill-of-lading fee is exactly the kind of quiet
    nonsense a review is supposed to be spared.
    """
    stripped = TRAILING_NOISE_RE.sub("", line.rstrip())
    matches = list(AMOUNT_RE.finditer(stripped))
    if not matches or matches[-1].end() != len(stripped):
        return None
    return parse_amount(matches[-1].group(0))


def find_currency(text: str) -> str | None:
    match = CURRENCY_RE.search(text)
    if not match:
        return None
    return match.group(1) or CURRENCY_SYMBOLS.get(match.group(2) or "")


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

        currency = find_currency(text) or context.base_currency
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
                continue
            charges.append(
                ExtractedLine(
                    description=raw,
                    amount=f"{amount:.2f}",
                    currency=find_currency(raw) or currency,
                    cost_type=cost_type,
                    container_number=next(iter(containers_in(raw)), None),
                    confidence=0.6,
                )
            )

        vendor = next((ln for ln in lines[:3] if not ln.upper().startswith(("FACTURE", "INVOICE"))), None)
        return FreightInvoice(
            vendor=vendor,
            invoice_number=invoice_number,
            invoice_date=find_date(text),
            currency=currency,
            total=f"{total:.2f}" if total is not None else None,
            vat=f"{vat:.2f}" if vat is not None else None,
            lines=charges,
            container_numbers=containers_in(text),
            bl_numbers=[m.group(1) for m in BL_RE.finditer(text)],
            po_numbers=[m.group(1).upper() for m in PO_RE.finditer(text)],
            confidence=0.6 if charges else 0.2,
            notes=[] if charges else ["No charge line recognised; every amount needs entering by hand."],
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
        """
        if total is not None and subtotal is not None and total >= subtotal:
            return total - subtotal
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
        """The amount on the last line naming one of these words. Invoices repeat their totals."""
        found: Decimal | None = None
        for raw, upper in zip(lines, upper_lines, strict=True):
            if any(word in upper for word in exclude):
                continue
            if any(word in upper for word in words):
                amount = last_amount(raw)
                if amount is not None:
                    found = amount
        return found
