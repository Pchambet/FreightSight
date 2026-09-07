from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, status

from app.api.v1 import schemas
from app.api.v1.deps import FxDep, WriterDep
from app.core.errors import Unprocessable
from app.core.money import q2, to_base
from app.core.tenancy import TenantDep, TenantSession
from app.domain.costing.engine import DUTIABLE
from app.domain.costing.service import recompute_org
from app.domain.fx.service import FxService
from app.domain.models import (
    AllocationMethod,
    Container,
    ContainerLoad,
    Cost,
    CostScope,
    CostType,
    PurchaseOrder,
    PurchaseOrderLine,
    Shipment,
)

router = APIRouter(prefix="/costs", tags=["costs"])

_SCOPE_MODEL = {
    CostScope.SHIPMENT: (Shipment, "shipment_id", "Shipment"),
    CostScope.CONTAINER: (Container, "container_id", "Container"),
    CostScope.PO: (PurchaseOrder, "po_id", "Purchase order"),
    CostScope.PO_LINE: (PurchaseOrderLine, "po_line_id", "Purchase order line"),
}


def _target_lines(t: TenantSession, scope: CostScope, target_id: UUID) -> list[PurchaseOrderLine]:
    match scope:
        case CostScope.PO_LINE:
            return list(t.db.scalars(t.q(PurchaseOrderLine).where(PurchaseOrderLine.id == target_id)))
        case CostScope.PO:
            return list(t.db.scalars(t.q(PurchaseOrderLine).where(PurchaseOrderLine.po_id == target_id)))
        case CostScope.CONTAINER:
            return list(
                t.db.scalars(
                    t.q(PurchaseOrderLine)
                    .join(ContainerLoad, ContainerLoad.po_line_id == PurchaseOrderLine.id)
                    .where(ContainerLoad.container_id == target_id)
                )
            )
        case CostScope.SHIPMENT:
            return list(
                t.db.scalars(
                    t.q(PurchaseOrderLine)
                    .join(ContainerLoad, ContainerLoad.po_line_id == PurchaseOrderLine.id)
                    .join(Container, Container.id == ContainerLoad.container_id)
                    .where(Container.shipment_id == target_id)
                )
            )
    raise AssertionError(scope)


def default_method(
    t: TenantSession, scope: CostScope, target_id: UUID, cost_type: CostType
) -> AllocationMethod:
    """Written on the cost, never implicit at compute time."""
    if cost_type is CostType.CUSTOMS_DUTY:
        lines = _target_lines(t, scope, target_id)
        if lines and all(ln.duty_rate is not None for ln in lines):
            return AllocationMethod.BY_THEORETICAL_DUTY
        return AllocationMethod.BY_CIF_VALUE
    return t.org.default_allocation_method


def _check_method(method: AllocationMethod, cost_type: CostType) -> None:
    duty_like = method in (AllocationMethod.BY_CIF_VALUE, AllocationMethod.BY_THEORETICAL_DUTY)
    if duty_like and cost_type is not CostType.CUSTOMS_DUTY:
        raise Unprocessable(f"{method.value} is reserved for CUSTOMS_DUTY costs", code="METHOD_NOT_ALLOWED")
    if cost_type in DUTIABLE and duty_like:
        raise Unprocessable("A dutiable cost cannot be allocated on a CIF basis", code="METHOD_NOT_ALLOWED")


def _apply_fx(t: TenantSession, fx: FxService, cost: Cost, manual_rate: Decimal | None) -> None:
    resolved = fx.resolve(t.db, t.org.base_currency, cost.currency, cost.cost_date, manual_rate)
    cost.fx_rate, cost.fx_date, cost.fx_source = resolved.rate, resolved.rate_date, resolved.source
    cost.amount_base = to_base(cost.amount, cost.fx_rate)


@router.get("", response_model=list[schemas.CostResponse])
def list_costs(
    t: TenantDep,
    scope: CostScope | None = None,
    target_id: UUID | None = None,
    cost_type: CostType | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[Cost]:
    stmt = t.q(Cost)
    if scope:
        stmt = stmt.where(Cost.scope == scope)
    if target_id:
        stmt = stmt.where(
            (Cost.shipment_id == target_id)
            | (Cost.container_id == target_id)
            | (Cost.po_id == target_id)
            | (Cost.po_line_id == target_id)
        )
    if cost_type:
        stmt = stmt.where(Cost.cost_type == cost_type)
    if date_from:
        stmt = stmt.where(Cost.cost_date >= date_from)
    if date_to:
        stmt = stmt.where(Cost.cost_date <= date_to)
    return list(t.db.scalars(stmt.order_by(Cost.cost_date.desc(), Cost.created_at.desc())))


@router.post("", response_model=schemas.CostResponse, status_code=status.HTTP_201_CREATED)
def create_cost(payload: schemas.CostCreate, t: TenantDep, fx: FxDep, p: WriterDep) -> Cost:
    model, fk, what = _SCOPE_MODEL[payload.scope]
    t.get_or_404(model, payload.target_id, what)
    method = payload.allocation_method or default_method(
        t, payload.scope, payload.target_id, payload.cost_type
    )
    _check_method(method, payload.cost_type)
    cost = Cost(
        scope=payload.scope,
        cost_type=payload.cost_type,
        amount=q2(payload.amount),
        currency=payload.currency,
        cost_date=payload.cost_date,
        allocation_method=method,
        manual_splits=[s.model_dump(mode="json") for s in payload.manual_splits]
        if payload.manual_splits
        else None,
        vendor=payload.vendor,
        invoice_number=payload.invoice_number,
        notes=payload.notes,
        created_by=p.user_id,
    )
    setattr(cost, fk, payload.target_id)
    _apply_fx(t, fx, cost, payload.fx_rate)
    t.add(cost)
    t.db.flush()
    recompute_org(t.db, t.org)
    t.db.commit()
    t.db.refresh(cost)
    return cost


@router.get("/{cost_id}", response_model=schemas.CostResponse)
def get_cost(cost_id: UUID, t: TenantDep) -> Cost:
    return t.get_or_404(Cost, cost_id, "Cost")


@router.patch("/{cost_id}", response_model=schemas.CostResponse)
def update_cost(cost_id: UUID, payload: schemas.CostUpdate, t: TenantDep, fx: FxDep, _: WriterDep) -> Cost:
    cost = t.get_or_404(Cost, cost_id, "Cost")
    changes = payload.model_dump(exclude_unset=True)
    splits = changes.pop("manual_splits", None)
    manual_rate = changes.pop("fx_rate", None)
    for k, v in changes.items():
        if k == "amount":
            v = q2(v)
        setattr(cost, k, v)
    if payload.allocation_method is not None or splits is not None:
        if cost.allocation_method is AllocationMethod.MANUAL:
            if splits is None and cost.manual_splits is None:
                raise Unprocessable("manual_splits is required for MANUAL", code="MANUAL_SPLITS_REQUIRED")
            if splits is not None:
                if sum(Decimal(str(s["pct"])) for s in splits) != Decimal("100.00"):
                    raise Unprocessable("manual_splits must sum to 100.00", code="INVALID_MANUAL_SPLIT")
                cost.manual_splits = [
                    {"target_type": s["target_type"], "target_id": str(s["target_id"]), "pct": str(s["pct"])}
                    for s in splits
                ]
        else:
            cost.manual_splits = None
        _check_method(cost.allocation_method, cost.cost_type)
    if any(k in changes for k in ("amount", "currency", "cost_date")) or manual_rate is not None:
        _apply_fx(t, fx, cost, manual_rate)
    t.db.flush()
    recompute_org(t.db, t.org)
    t.db.commit()
    t.db.refresh(cost)
    return cost


@router.delete("/{cost_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cost(cost_id: UUID, t: TenantDep, _: WriterDep) -> None:
    cost = t.get_or_404(Cost, cost_id, "Cost")
    t.db.delete(cost)
    t.db.flush()
    recompute_org(t.db, t.org)
    t.db.commit()
