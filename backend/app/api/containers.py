from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app import schemas
from app.costing import LinkInput, allocate_container, quantize_cent
from app.deps import DbDep, OrgDep
from app.models import Container, ContainerPurchaseOrder, Cost, Organization

router = APIRouter(prefix="/api/containers", tags=["containers"])


def _get_container(db: DbDep, org: Organization, container_id: UUID) -> Container:
    container = db.scalar(
        select(Container)
        .where(Container.id == container_id, Container.org_id == org.id)
        .options(
            selectinload(Container.po_links).selectinload(ContainerPurchaseOrder.purchase_order),
            selectinload(Container.costs),
        )
    )
    if container is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Container not found")
    return container


@router.get("", response_model=list[schemas.ContainerResponse])
def list_containers(db: DbDep, org: OrgDep) -> list[Container]:
    return list(
        db.scalars(select(Container).where(Container.org_id == org.id).order_by(Container.container_number))
    )


@router.post("", response_model=schemas.ContainerResponse, status_code=status.HTTP_201_CREATED)
def create_container(payload: schemas.ContainerCreate, db: DbDep, org: OrgDep) -> Container:
    existing = db.scalar(
        select(Container).where(
            Container.org_id == org.id, Container.container_number == payload.container_number
        )
    )
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Container already exists for this organization")
    container = Container(org_id=org.id, container_number=payload.container_number, carrier=payload.carrier)
    db.add(container)
    db.commit()
    db.refresh(container)
    return container


@router.patch("/{container_id}", response_model=schemas.ContainerResponse)
def update_container(
    container_id: UUID, payload: schemas.ContainerUpdate, db: DbDep, org: OrgDep
) -> Container:
    """Manual tracking until a real provider exists (Phase 2)."""
    container = _get_container(db, org, container_id)
    if payload.status is not None:
        container.status = payload.status
    if payload.carrier is not None:
        container.carrier = payload.carrier
    db.commit()
    db.refresh(container)
    return container


@router.post(
    "/{container_id}/costs", response_model=schemas.CostResponse, status_code=status.HTTP_201_CREATED
)
def add_cost(container_id: UUID, payload: schemas.CostCreate, db: DbDep, org: OrgDep) -> Cost:
    container = _get_container(db, org, container_id)
    if payload.currency != org.base_currency:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Cost currency {payload.currency} differs from the organization base currency "
            f"{org.base_currency}. Multi-currency costs with fixed FX rates arrive in Phase 1.",
        )
    cost = Cost(
        container_id=container.id,
        cost_type=payload.cost_type,
        amount=quantize_cent(payload.amount),
        currency=payload.currency,
    )
    db.add(cost)
    db.commit()
    db.refresh(cost)
    return cost


@router.post("/{container_id}/upload-invoice", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def upload_invoice(
    container_id: UUID, db: DbDep, org: OrgDep, file: UploadFile = File(...)
) -> dict[str, str]:
    """Invoice extraction is not built yet. It used to insert hard-coded amounts; it no longer does."""
    _get_container(db, org, container_id)
    return {
        "code": "NOT_IMPLEMENTED",
        "message": "Invoice extraction is planned for Phase 2. Add costs manually for now.",
        "filename": file.filename or "",
    }


@router.get("/{container_id}/landed-costs", response_model=schemas.LandedCostResponse)
def get_landed_costs(container_id: UUID, db: DbDep, org: OrgDep) -> schemas.LandedCostResponse:
    container = _get_container(db, org, container_id)
    costs = sorted(container.costs, key=lambda c: (c.cost_type.value, str(c.id)))
    total = quantize_cent(sum((c.amount for c in costs), Decimal("0")))

    links = [
        LinkInput(
            key=str(link.po_id),
            po_number=link.purchase_order.po_number,
            fob_value=link.purchase_order.total_value,
            allocation_pct=link.allocation_percentage,
        )
        for link in container.po_links
    ]
    outcome = allocate_container(total, links)

    by_key = {str(link.po_id): link for link in container.po_links}
    breakdown: list[schemas.LandedCostBreakdown] = []
    for key in sorted(outcome.parts, key=lambda k: (by_key[k].purchase_order.po_number, k)):
        link = by_key[key]
        po = link.purchase_order
        allocated = outcome.parts[key]
        pct = (allocated / total * 100).quantize(Decimal("0.01")) if total else Decimal("0.00")
        breakdown.append(
            schemas.LandedCostBreakdown(
                po_id=po.id,
                po_number=po.po_number,
                supplier_name=po.supplier_name,
                fob_value=po.total_value,
                allocation_pct=pct,
                allocated_costs=allocated,
                true_landed_cost=quantize_cent(po.total_value + allocated),
            )
        )

    return schemas.LandedCostResponse(
        container=schemas.ContainerResponse.model_validate(container),
        base_currency=org.base_currency,
        allocation_method=outcome.method,
        total_additional_costs=total,
        total_allocated=quantize_cent(sum(outcome.parts.values(), Decimal("0"))),
        unallocated=outcome.unallocated,
        breakdown=breakdown,
        raw_costs=[schemas.CostResponse.model_validate(c) for c in costs],
        warnings=[schemas.LandedCostWarning(code=w.code, message=w.message) for w in outcome.warnings],
    )
