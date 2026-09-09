"""Aggregate an engine computation into landed-cost reports (container, shipment, purchase order)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from app.core.money import q2, q4
from app.domain.costing import engine
from app.domain.costing.engine import EXCLUDED_FROM_LANDED
from app.domain.costing.service import Computation, to_engine_cost
from app.domain.models import Cost, CostStatus

ZERO = Decimal("0.00")


@dataclass
class CostTypeSplit:
    """One cost type on this scope, told in two columns: what was expected, what was invoiced."""

    estimated: Decimal = ZERO
    actual: Decimal = ZERO


@dataclass
class LineReport:
    load_id: UUID
    container_id: UUID
    container_number: str
    po_id: UUID
    po_number: str
    line_no: int
    sku: str | None
    description: str | None
    quantity: Decimal
    fob: Decimal
    allocated: Decimal  # excluding IMPORT_VAT
    vat: Decimal
    landed: Decimal
    unit_landed_cost: Decimal
    #: The split of `allocated` between estimates still standing in and invoices received.
    estimated: Decimal = ZERO
    actual: Decimal = ZERO
    #: Invoiced minus expected, on the estimates that have been replaced. Signed: positive is worse.
    variance: Decimal = ZERO
    by_cost_type: dict[str, Decimal] = field(default_factory=dict)


@dataclass
class Warning_:
    cost_id: UUID
    code: str
    message: str
    amount_base: Decimal
    load_ids: list[UUID] = field(default_factory=list)
    load_labels: list[str] = field(default_factory=list)


@dataclass
class Report:
    base_currency: str
    fob: Decimal
    allocated: Decimal
    vat: Decimal
    landed: Decimal
    unallocated: Decimal
    estimated: Decimal
    actual: Decimal
    variance: Decimal
    #: How much of this scope is invoiced rather than expected: the share of the cost types seen here
    #: that have a real cost. None when nothing is expected at all.
    completeness: Decimal | None
    by_cost_type: dict[str, Decimal]
    by_cost_type_detail: dict[str, CostTypeSplit]
    lines: list[LineReport]
    costs: list[Cost]
    warnings: list[Warning_]
    #: `(actual, the estimate it replaced)` inside this scope, which is where the variance comes from.
    replaced: list[tuple[Cost, Cost]] = field(default_factory=list)


def estimate_allocations(comp: Computation) -> dict[UUID, dict[UUID, Decimal]]:
    """Re-allocate the estimates that have been replaced, exactly as they were when they were live.

    This is what makes a line-level variance real rather than a proportion invented after the fact:
    the replaced estimate goes through the same engine, with its own scope and method, and the
    difference per line is the difference between two full allocations.
    """
    pairs = comp.superseded
    if not pairs:
        return {}
    costs = [to_engine_cost(estimate) for _, estimate in pairs]
    result = engine.allocate(costs, comp.loads, fallback_method="BY_VALUE")
    per_estimate: dict[UUID, dict[UUID, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
    for allocation in result.allocations:
        per_estimate[allocation.cost_id][allocation.load_id] += allocation.amount_base
    return per_estimate


def _report(comp: Computation, base_currency: str, load_filter: set[UUID], cost_filter: set[UUID]) -> Report:
    per_load: dict[UUID, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
    per_load_status: dict[UUID, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
    detail: dict[str, CostTypeSplit] = defaultdict(CostTypeSplit)
    for a in comp.result.allocations:
        if a.load_id in load_filter:
            cost = comp.cost_rows[a.cost_id]
            ct = cost.cost_type.value
            per_load[a.load_id][ct] += a.amount_base
            column = "estimated" if cost.status is CostStatus.ESTIMATE else "actual"
            per_load_status[a.load_id][column] += a.amount_base
            setattr(detail[ct], column, getattr(detail[ct], column) + a.amount_base)

    # The variance: each replaced estimate re-allocated, subtracted from the invoice that replaced it.
    replaced = [(actual, estimate) for actual, estimate in comp.superseded if actual.id in cost_filter]
    estimate_alloc = estimate_allocations(comp)
    variance_per_load: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
    for actual, estimate in replaced:
        for a in comp.result.allocations:
            if a.cost_id == actual.id and a.load_id in load_filter:
                variance_per_load[a.load_id] += a.amount_base
        for load_id, amount in estimate_alloc.get(estimate.id, {}).items():
            if load_id in load_filter:
                variance_per_load[load_id] -= amount
        detail[estimate.cost_type.value].estimated = (
            detail[estimate.cost_type.value].estimated + estimate.amount_base
        )

    lines: list[LineReport] = []
    for ld in comp.loads:
        if ld.id not in load_filter:
            continue
        row = comp.load_rows[ld.id]
        line = row.po_line
        po = line.purchase_order
        by_ct = dict(per_load.get(ld.id, {}))
        vat = sum((v for k, v in by_ct.items() if k in EXCLUDED_FROM_LANDED), ZERO)
        allocated = sum((v for k, v in by_ct.items() if k not in EXCLUDED_FROM_LANDED), ZERO)
        landed = q2(ld.fob + allocated)
        lines.append(
            LineReport(
                load_id=ld.id,
                container_id=ld.container_id,
                container_number=row.container.container_number,
                po_id=po.id,
                po_number=po.po_number,
                line_no=line.line_no,
                sku=line.sku,
                description=line.description,
                quantity=ld.quantity,
                fob=ld.fob,
                allocated=q2(allocated),
                vat=q2(vat),
                landed=landed,
                unit_landed_cost=q4(landed / ld.quantity),
                estimated=q2(per_load_status.get(ld.id, {}).get("estimated", ZERO)),
                actual=q2(per_load_status.get(ld.id, {}).get("actual", ZERO)),
                variance=q2(variance_per_load.get(ld.id, ZERO)),
                by_cost_type=by_ct,
            )
        )

    by_cost_type: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for ln in lines:
        for k, v in ln.by_cost_type.items():
            by_cost_type[k] += v

    costs = [comp.cost_rows[cid] for cid in cost_filter if cid in comp.cost_rows]
    costs.sort(key=lambda c: (c.cost_date, c.cost_type.value, str(c.id)))
    warnings = []
    for u in comp.result.unallocated:
        if u.cost_id not in cost_filter:
            continue
        message = u.message
        labels = [_load_label(comp, lid) for lid in u.load_ids if lid in comp.load_rows]
        if labels:
            message = f"{message}: {', '.join(labels)}"
        amount = comp.cost_rows[u.cost_id].amount_base
        warnings.append(Warning_(u.cost_id, u.code, message, amount, list(u.load_ids), labels))
    fob = sum((ln.fob for ln in lines), ZERO)
    allocated_total = sum((ln.allocated for ln in lines), ZERO)
    vat_total = sum((ln.vat for ln in lines), ZERO)
    return Report(
        base_currency=base_currency,
        fob=q2(fob),
        allocated=q2(allocated_total),
        vat=q2(vat_total),
        landed=q2(fob + allocated_total),
        unallocated=q2(sum((w.amount_base for w in warnings), ZERO)),
        estimated=q2(sum((ln.estimated for ln in lines), ZERO)),
        actual=q2(sum((ln.actual for ln in lines), ZERO)),
        variance=q2(sum((ln.variance for ln in lines), ZERO)),
        completeness=_completeness(comp, cost_filter, replaced),
        by_cost_type={k: q2(v) for k, v in sorted(by_cost_type.items())},
        by_cost_type_detail={
            k: CostTypeSplit(estimated=q2(v.estimated), actual=q2(v.actual))
            for k, v in sorted(detail.items())
        },
        lines=lines,
        costs=costs,
        warnings=warnings,
        replaced=replaced,
    )


def _completeness(
    comp: Computation, cost_filter: set[UUID], replaced: list[tuple[Cost, Cost]]
) -> Decimal | None:
    """The share of the cost types seen on this scope that have a real invoice behind them.

    Deliberately about *types*, not amounts: an organization wants to know which of the six things it
    expects to be billed for have arrived, and a large freight invoice should not make a missing
    customs bill look like a rounding error. Types only known through a replaced estimate count as
    invoiced, since their invoice is precisely what replaced them.
    """
    expected: set[str] = {comp.cost_rows[cid].cost_type.value for cid in cost_filter if cid in comp.cost_rows}
    invoiced: set[str] = {
        comp.cost_rows[cid].cost_type.value
        for cid in cost_filter
        if cid in comp.cost_rows and comp.cost_rows[cid].status is CostStatus.ACTUAL
    }
    for _, estimate in replaced:
        expected.add(estimate.cost_type.value)
    if not expected:
        return None
    return (Decimal(len(invoiced)) / Decimal(len(expected))).quantize(Decimal("0.01"))


def _load_label(comp: Computation, load_id: UUID) -> str:
    row = comp.load_rows[load_id]
    line = row.po_line
    label = f"{line.purchase_order.po_number} #{line.line_no}"
    return f"{label} {line.sku}" if line.sku else label


def container_report(comp: Computation, base_currency: str, container_id: UUID) -> Report:
    loads = {ld.id for ld in comp.loads if ld.container_id == container_id}
    shipment_id = next((ld.shipment_id for ld in comp.loads if ld.container_id == container_id), None)
    po_ids = {ld.po_id for ld in comp.loads if ld.container_id == container_id}
    line_ids = {ld.po_line_id for ld in comp.loads if ld.container_id == container_id}
    costs = {
        c.id
        for c in comp.cost_rows.values()
        if c.container_id == container_id
        or (shipment_id is not None and c.shipment_id == shipment_id)
        or c.po_id in po_ids
        or c.po_line_id in line_ids
    }
    return _report(comp, base_currency, loads, costs)


def shipment_report(comp: Computation, base_currency: str, shipment_id: UUID) -> Report:
    loads = {ld.id for ld in comp.loads if ld.shipment_id == shipment_id}
    container_ids = {ld.container_id for ld in comp.loads if ld.shipment_id == shipment_id}
    costs = {
        c.id
        for c in comp.cost_rows.values()
        if c.shipment_id == shipment_id or c.container_id in container_ids
    }
    return _report(comp, base_currency, loads, costs)


def purchase_order_report(comp: Computation, base_currency: str, po_id: UUID) -> Report:
    loads = {ld.id for ld in comp.loads if ld.po_id == po_id}
    line_ids = {ld.po_line_id for ld in comp.loads if ld.po_id == po_id}
    costs = {c.id for c in comp.cost_rows.values() if c.po_id == po_id or c.po_line_id in line_ids}
    costs |= {a.cost_id for a in comp.result.allocations if a.load_id in loads}  # what reached its lines
    return _report(comp, base_currency, loads, costs)
