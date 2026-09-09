"""Aggregate an engine computation into landed-cost reports (container, shipment, purchase order)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from app.core.money import q2, q4
from app.domain.costing.engine import EXCLUDED_FROM_LANDED
from app.domain.costing.service import Computation
from app.domain.models import Cost

ZERO = Decimal("0.00")


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
    by_cost_type: dict[str, Decimal]
    lines: list[LineReport]
    costs: list[Cost]
    warnings: list[Warning_]


def _report(comp: Computation, base_currency: str, load_filter: set[UUID], cost_filter: set[UUID]) -> Report:
    per_load: dict[UUID, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
    for a in comp.result.allocations:
        if a.load_id in load_filter:
            ct = comp.cost_rows[a.cost_id].cost_type.value
            per_load[a.load_id][ct] += a.amount_base

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
        by_cost_type={k: q2(v) for k, v in sorted(by_cost_type.items())},
        lines=lines,
        costs=costs,
        warnings=warnings,
    )


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
