"""Reading a costs ledger: what each forwarder, haulier and customs broker billed, and on which box.

A prospect's quarter has its costs in the accounts before it has them anywhere else: the purchase
journal's lines for the forwarders — date, supplier, invoice number, label, amount — sometimes with the
container or the bill of lading in a column, more often only in the label. Read as costs they make the
quarter's landed costs, and every euro misread is a margin misstated in the audit sold on them. So:

- Actual costs only. A file carries no estimates: an estimate keyed in a spreadsheet and the invoice
  that settles it would both count.
- The target is a box, a bill of lading or an order the organization already has — from a column, or
  read in the label (a container by its check digit) — never created here: a cost on a box nobody
  loaded is spread on nothing. A bill of lading with one box is that box.
- The type comes from a column, else from the label, else from what a person said for that label or
  for the whole file; a type not read from a column is `type_inferred`, and what the audit finds on
  such a cost is a question. A label naming several charges — « débours », « fret + THC » — is refused:
  it has to be split.
- An amount « TTC » is refused: import VAT is recovered, never a landed cost.
- A negative line is not a cost. One that cancels a line of the file cancels it (both out); any other
  is set aside and counted, never dropped in silence: it may refund a charge the audit would claim.
- The same invoice line never twice: identical lines of the file add up, what an earlier import of the
  same ledger wrote is recognised and left alone, an invoice already in the books or waiting in the
  inbox is refused, and a charge of the same type already on the same freight is refused unless a
  person says otherwise.
- An estimate of the same type on the same target is replaced by the cost, the pair becoming the
  variance; several, or one at the other end of the freight, are left to a person: never both counted.
- Every amount is converted at the ECB rate of its date, fixed on the cost like any other; a day with
  no rate is a refusal, not a guess.

The rules mirror those of the invoice's confirmation (`invoices.checks`), applied to the organization's
costs read once — a ledger has thousands of lines, and a query per rule per line is minutes.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select

from app.adapters.extraction.regex_extractor import (
    ACRONYM_RE,
    BL_RE,
    COST_ACRONYMS,
    COST_KEYWORDS,
    NOT_A_CHARGE_RE,
)
from app.core.errors import Unprocessable
from app.core.money import q2, to_base
from app.core.tenancy import TenantSession
from app.domain.boxes import container_numbers_in
from app.domain.costing import entry
from app.domain.costing.service import Computation, compute
from app.domain.fx.service import FxService
from app.domain.imports.containers import normalize_reference
from app.domain.imports.parsing import (
    ColumnDates,
    ColumnNumbers,
    ImportError_,
    Table,
    infer_date_orders,
    parse_date,
    parse_decimal,
)
from app.domain.imports.service import ImportReport, RowIssue, _Row
from app.domain.invoices.checks import note_field
from app.domain.labels import COST_TYPE_FR
from app.domain.models import (
    Container,
    Cost,
    CostScope,
    CostStatus,
    CostType,
    ImportJob,
    Invoice,
    InvoiceStatus,
    PurchaseOrder,
    PurchaseOrderLine,
    Shipment,
)

#: « Montant TTC », « Amount incl. VAT »: an amount with the tax in it. Import VAT is recovered.
_TAX_INCLUDED = re.compile(
    r"(?:^|[^a-z])(?:ttc|tvac|incl\w*[\s_.-]*vat|vat[\s_.-]*incl\w*|toutes[\s_]taxes)", re.I
)
_CURRENCY_CODE = re.compile(r"(?<![A-Z])(EUR|USD|GBP|CNY|CHF|JPY|HKD|SGD|AED)(?![A-Z])")
_SYMBOLS = {"€": "EUR", "$": "USD", "£": "GBP", "¥": "CNY"}
#: Labels that name several charges at once, whatever words they use: they have to be split.
_MIXED = re.compile(
    r"\bD[EÉ]BOURS\b|\bDROITS\s+ET\s+TAXES\b|\bDUTIES\s+AND\s+TAXES\b|\bDISBURSEMENTS?\b", re.I
)
#: Types a file may name in its type column: the code, and the names the application gives them.
_TYPE_NAMES: dict[str, CostType] = {
    **{kind.value.casefold(): kind for kind in CostType},
    **{name.casefold(): CostType(code) for code, name in COST_TYPE_FR.items()},
    **{kind.value.replace("_", " ").casefold(): kind for kind in CostType},
}
#: Freight whose customs value it is part of and whose duty it pays — decided like any other entry.
DUTY = CostType.CUSTOMS_DUTY
TOLERANCE = Decimal("0.02")


@dataclass
class _Read:
    """One row, read."""

    row: int
    scope: CostScope
    target_id: UUID
    target_label: str
    cost_type: CostType
    type_inferred: bool
    currency: str
    amount: Decimal
    amount_base: Decimal
    fx: tuple[Decimal, date, str]
    cost_date: date
    vendor: str | None
    invoice_number: str | None
    label: str | None


@dataclass
class _Group:
    """Rows of the file that are one cost: the same line of one invoice, said once or several times."""

    rows: list[_Read] = field(default_factory=list)

    @property
    def first(self) -> _Read:
        return self.rows[0]

    @property
    def amount(self) -> Decimal:
        return q2(sum((row.amount for row in self.rows), Decimal(0)))

    @property
    def amount_base(self) -> Decimal:
        return q2(sum((row.amount_base for row in self.rows), Decimal(0)))


def label_key(label: str) -> str:
    """A label as it groups: « THC MSCU4821994 » and « thc  TGHU7245086 » are one label, and the
    numbers of a file's references do not make one label per line."""
    text = BL_RE.sub(" ", label.upper())
    for number in container_numbers_in(text):
        text = text.replace(number, " ")
    return re.sub(r"\s+", " ", re.sub(r"\d+", "#", text)).strip().casefold()


def types_named(label: str) -> set[CostType]:
    """Every charge a label names, its references taken out first: « Fret B/L MEDU2604417 » is
    freight, not freight and a bill-of-lading fee."""
    text = BL_RE.sub(" ", label.upper())
    if NOT_A_CHARGE_RE.search(text):
        return set()
    found = {kind for keyword, kind in COST_KEYWORDS if keyword in text}
    found |= {dict(COST_ACRONYMS)[match.group(1)] for match in ACRONYM_RE.finditer(text)}
    return found


class _Books:
    """What the organization already has, read once: targets by reference, costs, invoices waiting."""

    def __init__(self, t: TenantSession) -> None:
        self.containers: dict[str, Container] = {
            c.container_number: c for c in t.db.scalars(t.q(Container).where(Container.archived_at.is_(None)))
        }
        self.shipments: dict[str, Shipment] = {
            normalize_reference(s.reference): s for s in t.db.scalars(t.q(Shipment))
        }
        self.boxes_of: dict[UUID, set[UUID]] = defaultdict(set)
        for container in self.containers.values():
            if container.shipment_id is not None:
                self.boxes_of[container.shipment_id].add(container.id)
        self.orders: dict[str, PurchaseOrder] = {
            order.po_number.upper(): order for order in t.db.scalars(t.q(PurchaseOrder))
        }
        self.order_of_line: dict[UUID, UUID] = dict(
            t.db.execute(
                select(PurchaseOrderLine.id, PurchaseOrderLine.po_id).where(
                    PurchaseOrderLine.org_id == t.org_id
                )
            )
            .tuples()
            .all()
        )
        self.shipment_of: dict[UUID, UUID | None] = {c.id: c.shipment_id for c in self.containers.values()}
        costs = list(t.db.scalars(t.q(Cost).where(Cost.closed_at.is_(None))))
        replaced = {cost.supersedes_cost_id for cost in costs if cost.supersedes_cost_id is not None}
        self.actuals = [cost for cost in costs if cost.status is CostStatus.ACTUAL]
        self.estimates = [
            cost for cost in costs if cost.status is CostStatus.ESTIMATE and cost.id not in replaced
        ]
        self.by_number: dict[str, list[Cost]] = defaultdict(list)
        for cost in self.actuals:
            if number := entry.normalize_invoice_number(cost.invoice_number):
                self.by_number[number].append(cost)
        # By what they are on, so that « the same freight » is a look-up and not a pass over the books:
        # a ledger has thousands of lines, and so do the books it is compared with.
        self.actuals_on: dict[UUID | None, list[Cost]] = defaultdict(list)
        self.estimates_on: dict[UUID | None, list[Cost]] = defaultdict(list)
        self.imported: dict[tuple[object, ...], list[Cost]] = defaultdict(list)
        for cost in self.actuals:
            self.actuals_on[_target_of(cost)].append(cost)
            if cost.import_job_id is not None:
                self.imported[_line_key(cost)].append(cost)
        for cost in self.estimates:
            self.estimates_on[_target_of(cost)].append(cost)
        self.lines_of: dict[UUID, set[UUID]] = defaultdict(set)
        for line_id, po_id in self.order_of_line.items():
            self.lines_of[po_id].add(line_id)
        self.inbox: dict[str, list[Invoice]] = defaultdict(list)
        for invoice in t.db.scalars(
            t.q(Invoice).where(
                Invoice.status.in_(
                    (InvoiceStatus.UPLOADED, InvoiceStatus.EXTRACTING, InvoiceStatus.NEEDS_REVIEW)
                )
            )
        ):
            if number := entry.normalize_invoice_number(invoice.invoice_number):
                self.inbox[number].append(invoice)

    def freight(self, scope: CostScope, target_id: UUID) -> list[UUID]:
        """Every target on the same freight as this one — the rule of `invoices.checks._same_freight`:
        a box and the bill it travels under, a bill and its boxes, an order and its lines."""
        if scope is CostScope.CONTAINER:
            shipment = self.shipment_of.get(target_id)
            return [target_id, *([shipment] if shipment else [])]
        if scope is CostScope.SHIPMENT:
            return [target_id, *self.boxes_of.get(target_id, set())]
        if scope is CostScope.PO:
            return [target_id, *self.lines_of.get(target_id, set())]
        order = self.order_of_line.get(target_id)
        return [target_id, *([order] if order else [])]

    def on_freight(
        self, index: dict[UUID | None, list[Cost]], scope: CostScope, target_id: UUID, cost_type: CostType
    ) -> list[Cost]:
        return [
            cost
            for target in self.freight(scope, target_id)
            for cost in index.get(target, [])
            if cost.cost_type is cost_type
        ]

    def same_freight(self, cost: Cost, scope: CostScope, target_id: UUID) -> bool:
        """The rule of `invoices.checks._same_freight`: a box and the bill it travels under, an order
        and its lines, are one freight."""
        if scope is CostScope.CONTAINER:
            shipment = self.shipment_of.get(target_id)
            return cost.container_id == target_id or (shipment is not None and cost.shipment_id == shipment)
        if scope is CostScope.SHIPMENT:
            return cost.shipment_id == target_id or cost.container_id in self.boxes_of.get(target_id, set())
        if scope is CostScope.PO:
            return cost.po_id == target_id or (
                cost.po_line_id is not None and self.order_of_line.get(cost.po_line_id) == target_id
            )
        order = self.order_of_line.get(target_id)
        return cost.po_line_id == target_id or (order is not None and cost.po_id == order)


def refuse_tax_included(mapping: dict[str, str]) -> None:
    column = mapping.get("amount") or ""
    if _TAX_INCLUDED.search(column):
        raise Unprocessable(
            f"Column {column!r} holds amounts with the tax in them; map the amount before tax",
            code="AMOUNT_INCLUDES_VAT",
            column=column,
        )


def _currency_of(text: str | None) -> str | None:
    if not text:
        return None
    if match := _CURRENCY_CODE.search(text.upper()):
        return match.group(1)
    return next((code for symbol, code in _SYMBOLS.items() if symbol in text), None)


def _money(raw: str) -> str:
    """« 1 234,56 € », « EUR 1.234,56 », « (285,00) »: the number, its sign kept, the rest dropped."""
    text = raw.strip()
    negative = (text.startswith("(") and text.endswith(")")) or text.endswith("-")
    text = text.rstrip("-")
    text = _CURRENCY_CODE.sub("", text.upper())
    text = re.sub(r"[€$£¥()\s]", lambda m: " " if m.group(0).isspace() else "", text).strip()
    return f"-{text.lstrip('-')}" if negative else text


def apply_costs(
    t: TenantSession,
    job: ImportJob,
    table: Table,
    mapping: dict[str, str],
    report: ImportReport,
    conventions: dict[str, ColumnNumbers],
    fx: FxService | None,
) -> list[UUID]:
    """Read the ledger and write its costs, in the caller's SAVEPOINT. Returns the costs written."""
    if fx is None:  # pragma: no cover - every route passes one
        raise Unprocessable("No exchange rates to convert the amounts with", code="FX_RATE_UNAVAILABLE")
    refuse_tax_included(mapping)
    options = job.options or {}
    default_type = CostType(options["default_cost_type"]) if options.get("default_cost_type") else None
    given = {label_key(label): CostType(kind) for label, kind in (options.get("label_types") or {}).items()}
    force_duplicates = bool(options.get("force_duplicates"))
    header_currency = _currency_of(mapping.get("amount"))
    books = _Books(t)
    orders = _date_orders(table, mapping, report)
    today = datetime.now(UTC).date()
    _preload_rates(t, fx, table, mapping, orders, header_currency)

    unknown: dict[str, list[tuple[int, str, Decimal]]] = defaultdict(list)
    lines: list[_Read] = []
    credits: list[_Read] = []
    for idx, raw in enumerate(table.rows, start=table.header_row + 1):
        r = _Row(idx, raw, mapping, report, conventions)
        read = _read(t, fx, r, books, orders, today, header_currency, default_type, given, unknown)
        if read is None:
            continue
        if read.amount < 0:
            credits.append(read)
        elif read.amount == 0:
            r.warn("amount", "ZERO_AMOUNT", "a line of nothing is not a cost")
            report.valid_rows += 1
        else:
            lines.append(read)

    reversed_pairs = _cancel_reversals(lines, credits, report)
    skipped_credits = [c for c in credits if c.row not in reversed_pairs]
    groups = _group(line for line in lines if line.row not in reversed_pairs)
    written, counters = _write(t, job, fx, books, groups, report, force_duplicates)
    report.valid_rows += len(skipped_credits)
    for credit in skipped_credits:
        report.warnings.append(
            RowIssue(
                credit.row,
                "amount",
                "CREDIT_NOTE_SKIPPED",
                "a negative line is not a cost; it is set aside and counted",
                {"amount": str(credit.amount), "currency": credit.currency},
            )
        )
    report.extra |= counters | {
        "unknown_labels": [
            {
                "label": entries[0][1],
                "rows": len(entries),
                "total_base": str(q2(sum((amount for _, _, amount in entries), Decimal(0)))),
            }
            for entries in unknown.values()
        ],
        "credit_notes_skipped": [
            {
                "row": c.row,
                "cost_date": c.cost_date.isoformat(),
                "vendor": c.vendor,
                "invoice_number": c.invoice_number,
                "amount": str(c.amount),
                "currency": c.currency,
                "amount_base": str(c.amount_base),
            }
            for c in skipped_credits
        ],
        "credit_notes_skipped_base": str(q2(sum((c.amount_base for c in skipped_credits), Decimal(0)))),
        "reversed_in_file": len(reversed_pairs) // 2,
    }
    return written


def _date_orders(table: Table, mapping: dict[str, str], report: ImportReport) -> dict[str, ColumnDates]:
    column = mapping.get("cost_date")
    orders = infer_date_orders(table, {column}) if column else {}
    read = orders.get(column) if column else None
    if read is not None and read.ambiguous:
        report.warnings.append(
            RowIssue(
                table.header_row,
                "cost_date",
                "DATE_ORDER_ASSUMED",
                f"In column {column!r} every date could be read either way; the day was read first",
                {"column": column, "example": read.example or "", "order": read.order},
            )
        )
    return orders


def _preload_rates(
    t: TenantSession,
    fx: FxService,
    table: Table,
    mapping: dict[str, str],
    orders: dict[str, ColumnDates],
    header_currency: str | None,
) -> None:
    """Every rate the file will ask for, in one call per currency: a courtesy, never a condition."""
    days: dict[str, list[date]] = defaultdict(list)
    date_column, currency_column = mapping.get("cost_date"), mapping.get("currency")
    for raw in table.rows:
        try:
            day = parse_date(
                raw.get(date_column or "", ""),
                order=orders[date_column].order if date_column in orders else "dmy",
            )
        except ImportError_:
            continue
        currency = (raw.get(currency_column or "", "") or "").strip().upper() or header_currency
        if day is not None and currency and currency != t.org.base_currency:
            days[currency].append(day)
    for currency, seen in days.items():
        fx.preload(t.db, t.org.base_currency, currency, min(seen), max(seen))


def _read(
    t: TenantSession,
    fx: FxService,
    r: _Row,
    books: _Books,
    orders: dict[str, ColumnDates],
    today: date,
    header_currency: str | None,
    default_type: CostType | None,
    given: dict[str, CostType],
    unknown: dict[str, list[tuple[int, str, Decimal]]],
) -> _Read | None:
    """One row, read — or None, with its errors said."""
    raw_date = r.text("cost_date")
    cost_date = None
    if raw_date is None:
        r.error("cost_date", "REQUIRED", "cost_date is empty")
    else:
        column = r.mapping.get("cost_date") or ""
        try:
            cost_date = parse_date(raw_date, order=orders[column].order if column in orders else "dmy")
        except ImportError_ as e:
            r.error("cost_date", e.code, e.message, value=raw_date)
        if cost_date is not None and cost_date > today:
            r.error(
                "cost_date",
                "DATE_IN_FUTURE",
                f"cost_date {cost_date.isoformat()} is still to come",
                value=raw_date,
            )

    raw_amount = r.text("amount")
    amount = None
    if raw_amount is None:
        r.error("amount", "REQUIRED", "amount is empty")
    else:
        column = r.mapping.get("amount") or ""
        convention = r.conventions.get(column)
        try:
            amount = parse_decimal(_money(raw_amount), comma=convention.comma if convention else "auto")
        except ImportError_ as e:
            r.error("amount", e.code, e.message, value=raw_amount)

    stated = (r.text("currency") or "").upper() or None
    in_amount = _currency_of(raw_amount)
    currency = stated or in_amount or header_currency or t.org.base_currency
    if stated is not None and (len(stated) != 3 or not stated.isalpha()):
        r.error("currency", "INVALID_CURRENCY", f"{stated!r} is not a 3-letter ISO code", value=stated)
    for other in (header_currency, in_amount):
        if stated and other and other != stated:
            r.error(
                "currency",
                "AMOUNT_CURRENCY_MISMATCH",
                f"the amount says {other} and the currency column {stated}",
                amount=other,
                currency=stated,
            )
            break

    target = _target(r, books)
    if r.failed or cost_date is None or amount is None or target is None:
        return None
    kind = _kind(r, default_type, given)
    if kind == UNKNOWN_LABEL:
        # Said with what hangs on it, so that a person types the label once for all its rows.
        label = r.text("label") or ""
        amount_base = _base(t, fx, r, currency, cost_date, amount)
        unknown[label_key(label)].append((r.row_no, label, amount_base or Decimal(0)))
        return None
    if not isinstance(kind, tuple):
        return None
    cost_type, inferred = kind
    rate = _rate(t, fx, r, currency, cost_date)
    if rate is None:
        return None
    scope, target_id, target_label = target
    return _Read(
        row=r.row_no,
        scope=scope,
        target_id=target_id,
        target_label=target_label,
        cost_type=cost_type,
        type_inferred=inferred,
        currency=currency,
        amount=q2(amount),
        amount_base=to_base(q2(amount), rate[0]),
        fx=rate,
        cost_date=cost_date,
        vendor=entry.none_if_blank(r.text("vendor")),
        invoice_number=entry.none_if_blank(r.text("invoice_number")),
        label=r.text("label"),
    )


def _rate(
    t: TenantSession, fx: FxService, r: _Row, currency: str, day: date
) -> tuple[Decimal, date, str] | None:
    try:
        resolved = fx.resolve(t.db, t.org.base_currency, currency, day)
    except Unprocessable:
        r.error(
            "currency",
            "FX_RATE_UNAVAILABLE",
            f"no {currency} rate is known for {day.isoformat()}",
            currency=currency,
            date=day.isoformat(),
        )
        return None
    return resolved.rate, resolved.rate_date, resolved.source


def _base(
    t: TenantSession, fx: FxService, r: _Row, currency: str, day: date, amount: Decimal
) -> Decimal | None:
    rate = _rate(t, fx, r, currency, day)
    return to_base(q2(amount), rate[0]) if rate is not None else None


def _target(r: _Row, books: _Books) -> tuple[CostScope, UUID, str] | None:
    """The box, bill or order a row is about: from its columns in that order, else from its label."""
    if (raw := r.text("container_number")) is not None:
        number = re.sub(r"[\s\-]", "", raw).upper()
        if (box := books.containers.get(number)) is None:
            r.error(
                "container_number",
                "UNKNOWN_CONTAINER",
                f"container {raw!r} is not known",
                value=raw,
            )
            return None
        return CostScope.CONTAINER, box.id, box.container_number
    if (raw := r.text("shipment_reference")) is not None:
        if (shipment := books.shipments.get(normalize_reference(raw))) is None:
            r.error(
                "shipment_reference",
                "UNKNOWN_SHIPMENT",
                f"bill of lading {raw!r} is not known",
                value=raw,
            )
            return None
        return _bill(books, shipment)
    if (raw := r.text("po_number")) is not None:
        if (order := books.orders.get(raw.strip().upper())) is None:
            r.error("po_number", "UNKNOWN_ORDER", f"order {raw!r} is not known", value=raw)
            return None
        return CostScope.PO, order.id, order.po_number
    label = r.text("label") or ""
    found = _in_label(label, books)
    if found is None:
        r.error(
            "label",
            "NO_TARGET",
            "no container, bill of lading or order is named on this row",
            value=label,
        )
        return None
    r.warn("label", "TARGET_FROM_LABEL", f"{found[2]} read in the label", value=found[2])
    return found


def _bill(books: _Books, shipment: Shipment) -> tuple[CostScope, UUID, str]:
    """A bill of lading with one box on it is that box: the per-box rules see the cost."""
    boxes = books.boxes_of.get(shipment.id, set())
    if len(boxes) == 1:
        (box_id,) = boxes
        box = next(c for c in books.containers.values() if c.id == box_id)
        return CostScope.CONTAINER, box.id, box.container_number
    return CostScope.SHIPMENT, shipment.id, shipment.reference


def _in_label(label: str, books: _Books) -> tuple[CostScope, UUID, str] | None:
    """A known container in the label, by its check digit; else a known bill or order named in it."""
    boxes = [books.containers[n] for n in container_numbers_in(label) if n in books.containers]
    if len(boxes) == 1:
        return CostScope.CONTAINER, boxes[0].id, boxes[0].container_number
    if boxes:
        return None  # several boxes named: which one is a person's call
    words = {normalize_reference(word) for word in re.findall(r"[A-Z0-9][A-Z0-9/\-]{3,}", label.upper())}
    bills = [books.shipments[w] for w in words if w in books.shipments]
    orders = [books.orders[w] for w in words if w in books.orders]
    if len(bills) == 1 and not orders:
        return _bill(books, bills[0])
    if len(orders) == 1 and not bills:
        return CostScope.PO, orders[0].id, orders[0].po_number
    return None


UNKNOWN_LABEL = "unknown_label"


def _kind(
    r: _Row, default_type: CostType | None, given: dict[str, CostType]
) -> tuple[CostType, bool] | str | None:
    """The type, and whether it was inferred rather than read in a column; UNKNOWN_LABEL for a label
    no rule and no person has typed yet, None for a row refused otherwise."""
    if (raw := r.text("cost_type")) is not None:
        kind = _TYPE_NAMES.get(re.sub(r"\s+", " ", raw.strip()).casefold())
        if kind is None:
            r.error("cost_type", "COST_TYPE_UNKNOWN", f"{raw!r} is not a cost type", value=raw)
            return None
        return kind, False
    label = r.text("label") or ""
    if _MIXED.search(label):
        r.error(
            "label", "COST_TYPE_AMBIGUOUS", f"{label!r} names several charges; split the line", value=label
        )
        return None
    named = types_named(label)
    if len(named) > 1:
        r.error(
            "label",
            "COST_TYPE_AMBIGUOUS",
            f"{label!r} names several charges; split the line",
            value=label,
            types=",".join(sorted(k.value for k in named)),
        )
        return None
    if named:
        return next(iter(named)), True
    if (kind := given.get(label_key(label))) is not None:
        return kind, True
    if default_type is not None:
        return default_type, True
    r.error("label", "COST_TYPE_UNKNOWN", "no cost type can be read on this row", value=label)
    return UNKNOWN_LABEL


def _cancel_reversals(lines: list[_Read], credits: list[_Read], report: ImportReport) -> set[int]:
    """A negative line that cancels a line of the file exactly — same target, type, currency and amount —
    takes it out with it: neither is a cost, and the pair is said."""
    out: set[int] = set()
    for credit in credits:
        match = next(
            (
                line
                for line in lines
                if line.row not in out
                and (line.scope, line.target_id, line.cost_type, line.currency)
                == (credit.scope, credit.target_id, credit.cost_type, credit.currency)
                and line.amount == -credit.amount
            ),
            None,
        )
        if match is None:
            continue
        out |= {match.row, credit.row}
        for row, other in ((match.row, credit.row), (credit.row, match.row)):
            report.errors.append(
                RowIssue(
                    row,
                    "amount",
                    "REVERSED_IN_FILE",
                    f"cancelled by row {other} of the same file",
                    {"row": other, "amount": str(match.amount), "currency": match.currency},
                )
            )
    return out


def _group(lines: Iterable[_Read]) -> list[_Group]:
    """Identical lines of one invoice are one cost: two THC of 285 on one box, one invoice, are 570."""
    groups: dict[tuple[object, ...], _Group] = {}
    for line in lines:
        number = entry.normalize_invoice_number(line.invoice_number)
        key = (
            line.scope,
            line.target_id,
            line.cost_type,
            line.currency,
            entry.normalize_vendor(line.vendor),
            number or None,
            None if number else line.cost_date,
        )
        groups.setdefault(key, _Group()).rows.append(line)
    return list(groups.values())


def _write(
    t: TenantSession,
    job: ImportJob,
    fx: FxService,
    books: _Books,
    groups: list[_Group],
    report: ImportReport,
    force_duplicates: bool,
) -> tuple[list[UUID], dict[str, object]]:
    matched: set[UUID] = set()
    written: list[Cost] = []
    rows_of: dict[UUID, int] = {}
    replaced_base = Decimal(0)
    duplicates: list[_Group] = []
    skipped = 0
    comp: Computation | None = None
    # Duty this file wrote, which the computation does not hold yet: by target, and by the lines each
    # covers. On the same target it is added as it stands; on another target covering the same lines —
    # a bill over its box — only a new computation knows its share, and one is made then, and only then.
    written_duty: dict[UUID, Decimal] = defaultdict(Decimal)
    duty_on_line: dict[UUID, UUID] = {}
    # Duty last: the customs value it is weighed against includes the freight of this very file.
    for group in sorted(groups, key=lambda g: g.first.cost_type is DUTY):
        first = group.first
        previous = _already_imported(books, group, matched)
        if previous is not None:
            matched.add(previous.id)
            skipped += 1
            report.valid_rows += len(group.rows)
            continue
        refusal = _already_in_books(books, group, force_duplicates)
        if refusal is not None:
            code, params = refusal
            duplicates.append(group)
            for row in group.rows:
                report.errors.append(RowIssue(row.row, "invoice_number", code, _SAID[code], params))
            continue
        estimates = books.on_freight(books.estimates_on, first.scope, first.target_id, first.cost_type)
        here = [e for e in estimates if _target_of(e) == first.target_id]
        if len(here) > 1 or len(estimates) > len(here):
            code = "SEVERAL_ESTIMATES" if len(here) > 1 else "ESTIMATE_OTHER_SCOPE"
            for row in group.rows:
                report.errors.append(
                    RowIssue(
                        row.row,
                        "cost_type",
                        code,
                        "an estimate of this type stands elsewhere on this freight; replace it by hand",
                        {"estimates": str(len(estimates)), "cost_type": first.cost_type.value},
                    )
                )
            continue
        amount_base = to_base(group.amount, first.fx[0])
        if first.cost_type is DUTY:
            if comp is None:
                t.db.flush()  # the file's freight is part of the customs value the duty is weighed on
                comp = compute(t.db, t.org)
            loads = {load.id for load in entry.loads_under(comp, first.scope, first.target_id)}
            if any(duty_on_line.get(line, first.target_id) != first.target_id for line in loads):
                t.db.flush()
                comp = compute(t.db, t.org)
                written_duty.clear()
                duty_on_line.clear()
            method = entry.default_method(
                t.db, t.org, first.scope, first.target_id, DUTY, amount_base, comp,
                pending=written_duty[first.target_id],
            )  # fmt: skip
            written_duty[first.target_id] += amount_base
            duty_on_line |= dict.fromkeys(loads, first.target_id)
        else:
            method = entry.default_method(t.db, t.org, first.scope, first.target_id, first.cost_type)
        cost = Cost(
            id=uuid4(),
            scope=first.scope,
            status=CostStatus.ACTUAL,
            cost_type=first.cost_type,
            amount=group.amount,
            currency=first.currency,
            fx_rate=first.fx[0],
            fx_date=first.fx[1],
            fx_source=first.fx[2],
            amount_base=amount_base,
            allocation_method=method,
            cost_date=min(row.cost_date for row in group.rows),
            vendor=first.vendor,
            invoice_number=first.invoice_number,
            notes=(
                f"From {job.original_filename or 'a costs file'} "
                f"{'rows' if len(group.rows) > 1 else 'row'} {', '.join(str(r.row) for r in group.rows)}"
            ),
            import_job_id=job.id,
            type_inferred=any(row.type_inferred for row in group.rows),
        )
        setattr(cost, _KEY[first.scope], first.target_id)
        if here:
            cost.supersedes_cost_id = here[0].id
            books.estimates_on[first.target_id].remove(here[0])
            replaced_base += here[0].amount_base
        t.add(cost)
        written.append(cost)
        rows_of[cost.id] = len(group.rows)
        report.valid_rows += len(group.rows)

    t.db.flush()
    by_type: dict[CostType, list[Cost]] = defaultdict(list)
    by_currency: dict[str, list[Cost]] = defaultdict(list)
    for cost in written:
        by_type[cost.cost_type].append(cost)
        by_currency[cost.currency].append(cost)

    counters: dict[str, object] = {
        "costs_created": len(written),
        "costs_skipped": skipped,
        "estimates_replaced": sum(1 for cost in written if cost.supersedes_cost_id is not None),
        "estimates_replaced_base": str(q2(replaced_base)),
        "duplicates": sum(len(g.rows) for g in duplicates),
        "duplicates_base": str(q2(sum((g.amount_base for g in duplicates), Decimal(0)))),
        "money": {
            "total_base": str(q2(sum((c.amount_base for c in written), Decimal(0)))),
            "by_type": [
                {
                    "cost_type": kind.value,
                    "rows": sum(rows_of[c.id] for c in costs),
                    "total_base": str(q2(sum((c.amount_base for c in costs), Decimal(0)))),
                }
                for kind, costs in sorted(by_type.items(), key=lambda item: item[0].value)
            ],
            "by_currency": [
                {
                    "currency": currency,
                    "rows": sum(rows_of[c.id] for c in costs),
                    "total": str(q2(sum((c.amount for c in costs), Decimal(0)))),
                    "total_base": str(q2(sum((c.amount_base for c in costs), Decimal(0)))),
                }
                for currency, costs in sorted(by_currency.items())
            ],
        },
    }
    return [cost.id for cost in written], counters


_KEY = {
    CostScope.CONTAINER: "container_id",
    CostScope.SHIPMENT: "shipment_id",
    CostScope.PO: "po_id",
    CostScope.PO_LINE: "po_line_id",
}
_SAID = {
    "INVOICE_ALREADY_RECORDED": "this invoice is already in the books",
    "INVOICE_IN_INBOX": "this invoice is waiting in the inbox; confirm or reject it there",
    "DUPLICATE_COST": "a charge of this type is already recorded on this freight",
}


def _target_of(cost: Cost) -> UUID | None:
    return cost.container_id or cost.shipment_id or cost.po_id or cost.po_line_id


def _line_key(cost: Cost) -> tuple[object, ...]:
    return (
        _target_of(cost),
        cost.cost_type,
        cost.currency,
        cost.amount,
        cost.cost_date,
        entry.normalize_invoice_number(cost.invoice_number),
    )


def _already_imported(books: _Books, group: _Group, matched: set[UUID]) -> Cost | None:
    """The cost an earlier import of the same ledger wrote for this very line: the same target, type,
    amount, currency and day, and the same invoice — or no invoice number on either. Each is matched
    once: two identical lines are two costs only if the books hold two."""
    first = group.first
    key = (
        first.target_id,
        first.cost_type,
        first.currency,
        group.amount,
        min(row.cost_date for row in group.rows),
        entry.normalize_invoice_number(first.invoice_number),
    )
    return next((cost for cost in books.imported.get(key, []) if cost.id not in matched), None)


def _already_in_books(books: _Books, group: _Group, force: bool) -> tuple[str, dict[str, str]] | None:
    """The refusals of the invoice's confirmation, read on the books: the invoice already recorded
    (`invoice_recorded`), waiting in the inbox, or a charge of this type already on this freight
    (`duplicate_cost_note`, which a person may overrule)."""
    first = group.first
    number = entry.normalize_invoice_number(first.invoice_number)
    wanted = entry.normalize_vendor(first.vendor)
    if number:
        for cost in books.by_number.get(number, []):
            theirs = entry.normalize_vendor(cost.vendor)
            if (wanted and theirs and wanted == theirs) or (
                not (wanted and theirs) and books.same_freight(cost, first.scope, first.target_id)
            ):
                return "INVOICE_ALREADY_RECORDED", _recorded(cost)
        for invoice in books.inbox.get(number, []):
            theirs = entry.normalize_vendor(invoice.vendor)
            if not wanted or not theirs or wanted == theirs:
                return "INVOICE_IN_INBOX", {
                    "invoice_id": str(invoice.id),
                    "invoice_number": invoice.invoice_number or "",
                }
    if not force:
        for cost in books.on_freight(books.actuals_on, first.scope, first.target_id, first.cost_type):
            return "DUPLICATE_COST", _recorded(cost)
    return None


def _recorded(cost: Cost) -> dict[str, str]:
    return {
        "cost_type": cost.cost_type.value,
        "vendor": note_field(cost.vendor),
        "invoice_number": note_field(cost.invoice_number),
        "amount_base": str(cost.amount_base),
        "scope": cost.scope.value,
    }
