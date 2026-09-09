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

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import selectinload

from app.core.tenancy import TenantDep
from app.domain.costing.service import compute
from app.domain.models import (
    Container,
    ContainerLoad,
    Cost,
    PurchaseOrder,
    PurchaseOrderLine,
)
from app.domain.reporting.service import arrival_date

router = APIRouter(prefix="/exports", tags=["exports"])

Locale = Literal["fr", "en"]
#: Excel on a French locale reads a bare UTF-8 file as Latin-1 unless it finds this.
BOM = "﻿"


def dialect(locale: Locale) -> tuple[str, str]:
    """The separator and the decimal mark this locale's spreadsheet expects."""
    return (";", ",") if locale == "fr" else (",", ".")


def number(value: Decimal | float | int | None, decimal_mark: str, places: int = 2) -> str:
    if value is None:
        return ""
    text = f"{Decimal(str(value)):.{places}f}"
    return text.replace(".", decimal_mark) if decimal_mark != "." else text


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
        writer.writerow(row)
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
    """One row per load: the whole landed cost, at the level it is computed."""
    _, mark = dialect(locale)
    comp = compute(t.db, t.org)
    per_load: dict[Any, dict[str, Decimal]] = {}
    for allocation in comp.result.allocations:
        cost = comp.cost_rows[allocation.cost_id]
        per_load.setdefault(allocation.load_id, {}).setdefault(cost.cost_type.value, Decimal("0.00"))
        per_load[allocation.load_id][cost.cost_type.value] += allocation.amount_base

    cost_types = sorted({ct for by_type in per_load.values() for ct in by_type})
    header = [
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
        "landed",
        "unit_landed_cost",
        *cost_types,
    ]

    def rows() -> Iterator[list[Any]]:
        for load in comp.loads:
            row = comp.load_rows[load.id]
            container = row.container
            landed_on = arrival_date(container)
            if not _within(landed_on, period_from, period_to):
                continue
            by_type = per_load.get(load.id, {})
            allocated = sum(by_type.values(), Decimal("0.00"))
            landed = load.fob + allocated
            line = row.po_line
            supplier = line.purchase_order.supplier
            yield [
                container.container_number,
                landed_on.isoformat() if landed_on else "",
                container.shipment.reference if container.shipment else "",
                supplier.name if supplier else "",
                line.purchase_order.po_number,
                line.line_no,
                line.sku or "",
                line.description or "",
                number(load.quantity, mark, 4),
                number(load.fob, mark),
                number(allocated, mark),
                number(landed, mark),
                number(landed / load.quantity if load.quantity else 0, mark, 4),
                *[number(by_type.get(ct), mark) for ct in cost_types],
            ]

    return csv_response(rows(), header, locale, "landed-costs.csv")


@router.get("/costs.csv")
def costs_csv(
    t: TenantDep,
    locale: Locale = "fr",
    period_from: date | None = None,
    period_to: date | None = None,
) -> StreamingResponse:
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
    ]

    def rows() -> Iterator[list[Any]]:
        for cost in t.db.scalars(stmt):
            target = cost.shipment_id or cost.container_id or cost.po_id or cost.po_line_id
            yield [
                cost.cost_date.isoformat(),
                cost.status.value,
                cost.cost_type.value,
                cost.scope.value,
                str(target) if target else "",
                cost.vendor or "",
                cost.invoice_number or "",
                number(cost.amount, mark),
                cost.currency,
                number(cost.fx_rate, mark, 8),
                number(cost.amount_base, mark),
                cost.allocation_method.value,
                str(cost.supersedes_cost_id) if cost.supersedes_cost_id else "",
            ]

    return csv_response(rows(), header, locale, "costs.csv")


@router.get("/purchase-orders.csv")
def purchase_orders_csv(
    t: TenantDep,
    locale: Locale = "fr",
    period_from: date | None = None,
    period_to: date | None = None,
) -> StreamingResponse:
    """One row per purchase-order line, which is the level anything is decided at."""
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
            ]

    return csv_response(rows(), header, locale, "containers.csv")
