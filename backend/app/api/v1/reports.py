"""Reports that answer a question someone actually asks at month end."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.v1 import schemas
from app.core.money import q2
from app.core.tenancy import TenantDep
from app.domain.costing.report import estimate_allocations
from app.domain.costing.service import compute

router = APIRouter(prefix="/reports", tags=["reports"])

ZERO = Decimal("0.00")


def month_bounds(period: str) -> tuple[date, date]:
    year, month = int(period[:4]), int(period[5:7])
    start = date(year, month, 1)
    end = date(year + (month == 12), (month % 12) + 1, 1)
    return start, end


@router.get("/variance", response_model=schemas.VarianceReport)
def variance(
    t: TenantDep,
    period: str = Query(pattern=r"^\d{4}-\d{2}$", description="YYYY-MM"),
) -> schemas.VarianceReport:
    """Estimated against invoiced, for the invoices dated in one month.

    Grouped by cost type and by purchase order, because those are the two questions: which charge
    surprised us, and which order carries the surprise. The split by order is the engine's own
    allocation of each invoice, not a proportion invented here.
    """
    start, end = month_bounds(period)
    comp = compute(t.db, t.org)
    estimate_alloc = estimate_allocations(comp)

    by_type: dict[str, list[Decimal]] = defaultdict(lambda: [ZERO, ZERO])
    by_po: dict[UUID, list[Decimal]] = defaultdict(lambda: [ZERO, ZERO])
    po_numbers: dict[UUID, str] = {}
    pairs = 0

    for actual, estimate in comp.superseded:
        if not (start <= actual.cost_date < end):
            continue
        pairs += 1
        by_type[actual.cost_type.value][1] += actual.amount_base
        by_type[estimate.cost_type.value][0] += estimate.amount_base

        for allocation in comp.result.allocations:
            if allocation.cost_id != actual.id:
                continue
            po_id = comp.load_rows[allocation.load_id].po_line.po_id
            by_po[po_id][1] += allocation.amount_base
        for load_id, amount in estimate_alloc.get(estimate.id, {}).items():
            po_id = comp.load_rows[load_id].po_line.po_id
            by_po[po_id][0] += amount

    for po_id in by_po:
        po = comp.pos.get(po_id)
        po_numbers[po_id] = po.po_number if po is not None else str(po_id)

    estimated = sum((values[0] for values in by_type.values()), ZERO)
    actual_total = sum((values[1] for values in by_type.values()), ZERO)
    return schemas.VarianceReport(
        period=period,
        base_currency=t.org.base_currency,
        estimated=q2(estimated),
        actual=q2(actual_total),
        variance=q2(actual_total - estimated),
        pairs=pairs,
        by_cost_type=[
            schemas.VarianceRow(
                key=cost_type,
                label=cost_type,
                estimated=q2(values[0]),
                actual=q2(values[1]),
                variance=q2(values[1] - values[0]),
            )
            for cost_type, values in sorted(by_type.items())
        ],
        by_purchase_order=[
            schemas.VarianceRow(
                key=str(po_id),
                label=po_numbers[po_id],
                estimated=q2(values[0]),
                actual=q2(values[1]),
                variance=q2(values[1] - values[0]),
            )
            for po_id, values in sorted(by_po.items(), key=lambda item: po_numbers[item[0]])
        ],
    )
