"""Bridge between the ORM and the pure engine.

`compute()` builds the engine inputs for one organization and runs it. `recompute_org()` does the same and
materialises the result into `cost_allocations`, in the caller's transaction. At SMB volume (thousands of
loads) a full-organization recompute is a few milliseconds, which is simpler and safer than scope tracking.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.core.money import q4
from app.domain.costing import engine
from app.domain.models import (
    AllocationMethod,
    Container,
    ContainerLoad,
    Cost,
    CostAllocation,
    CostType,
    Organization,
    PurchaseOrder,
    PurchaseOrderLine,
)


@dataclass
class Computation:
    loads: list[engine.Load]
    costs: list[engine.Cost]
    result: engine.AllocationResult
    load_rows: dict[UUID, ContainerLoad]
    cost_rows: dict[UUID, Cost]
    containers: dict[UUID, Container]
    lines: dict[UUID, PurchaseOrderLine]
    pos: dict[UUID, PurchaseOrder]


def _load_rows(db: Session, org_id: UUID) -> list[ContainerLoad]:
    stmt = (
        select(ContainerLoad)
        .where(ContainerLoad.org_id == org_id)
        .options(
            selectinload(ContainerLoad.container),
            selectinload(ContainerLoad.po_line).selectinload(PurchaseOrderLine.purchase_order),
        )
    )
    return list(db.scalars(stmt))


def _cost_rows(db: Session, org_id: UUID) -> list[Cost]:
    return list(db.scalars(select(Cost).where(Cost.org_id == org_id)))


def to_engine_load(row: ContainerLoad) -> engine.Load:
    line = row.po_line
    po = line.purchase_order
    return engine.Load(
        id=row.id,
        container_id=row.container_id,
        shipment_id=row.container.shipment_id,
        po_id=po.id,
        po_line_id=line.id,
        quantity=row.quantity,
        unit_price_base=q4(line.unit_price * po.fx_rate),
        unit_weight_kg=line.unit_weight_kg,
        unit_volume_cbm=line.unit_volume_cbm,
        duty_rate=line.duty_rate,
        sort_key=(row.container.container_number, po.po_number, line.line_no),
    )


def to_engine_cost(row: Cost, method_override: str | None = None) -> engine.Cost:
    target = row.shipment_id or row.container_id or row.po_id or row.po_line_id
    assert target is not None
    splits = tuple(
        engine.ManualSplit(s["target_type"], UUID(str(s["target_id"])), Decimal(str(s["pct"])))
        for s in (row.manual_splits or [])
    )
    method = method_override or row.allocation_method.value
    if method != "MANUAL":
        splits = ()
    return engine.Cost(
        id=row.id,
        scope=row.scope.value,
        target_id=target,
        cost_type=row.cost_type.value,
        amount_base=row.amount_base,
        method=method,
        manual_splits=splits,
    )


def compute(
    db: Session,
    org: Organization,
    *,
    method_overrides: Mapping[CostType, AllocationMethod] | None = None,
) -> Computation:
    """Run the engine over the whole organization. `method_overrides` (per cost type) is for previews."""
    load_rows = _load_rows(db, org.id)
    cost_rows = _cost_rows(db, org.id)
    overrides = method_overrides or {}
    loads = [to_engine_load(r) for r in load_rows]
    costs = [
        to_engine_cost(r, overrides[r.cost_type].value if r.cost_type in overrides else None)
        for r in cost_rows
    ]
    result = engine.allocate(costs, loads, fallback_method=org.default_allocation_method.value)
    return Computation(
        loads=loads,
        costs=costs,
        result=result,
        load_rows={r.id: r for r in load_rows},
        cost_rows={r.id: r for r in cost_rows},
        containers={r.container.id: r.container for r in load_rows},
        lines={r.po_line.id: r.po_line for r in load_rows},
        pos={r.po_line.purchase_order.id: r.po_line.purchase_order for r in load_rows},
    )


def recompute_org(db: Session, org: Organization) -> Computation:
    """Recompute and materialise allocations for the organization, inside the current transaction."""
    comp = compute(db, org)
    db.execute(delete(CostAllocation).where(CostAllocation.org_id == org.id))
    db.add_all(
        CostAllocation(
            org_id=org.id, cost_id=a.cost_id, container_load_id=a.load_id, amount_base=a.amount_base
        )
        for a in comp.result.allocations
    )
    db.flush()
    return comp
