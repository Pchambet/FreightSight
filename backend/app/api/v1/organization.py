from __future__ import annotations

from fastapi import APIRouter, status

from app.api.v1 import schemas
from app.api.v1.deps import WriterDep
from app.core.auth import PrincipalDep
from app.core.errors import Conflict
from app.core.tenancy import TenantDep
from app.domain.alerts.service import unread_count
from app.domain.costing.service import recompute_org
from app.domain.sample_data import has_data, seed_sample_data
from app.domain.tracking.state import derive_dnd

router = APIRouter(tags=["organization"])


@router.get("/me", response_model=schemas.MeResponse)
def me(p: PrincipalDep) -> schemas.MeResponse:
    return schemas.MeResponse(org_id=p.org_id, user_id=p.user_id, role=p.role, via=p.via)


def _organization(t: TenantDep) -> schemas.OrganizationResponse:
    response = schemas.OrganizationResponse.model_validate(t.org)
    response.unread_alerts = unread_count(t.db, t.org_id)
    return response


@router.get("/organization", response_model=schemas.OrganizationResponse)
def get_organization(t: TenantDep) -> schemas.OrganizationResponse:
    return _organization(t)


@router.patch("/organization", response_model=schemas.OrganizationResponse)
def update_organization(
    payload: schemas.OrganizationUpdate, t: TenantDep, _: WriterDep
) -> schemas.OrganizationResponse:
    changes = payload.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(t.org, k, v)
    if "default_allocation_method" in changes:
        recompute_org(t.db, t.org)
    t.db.commit()
    t.db.refresh(t.org)
    return _organization(t)


@router.post(
    "/organization/sample-data",
    response_model=schemas.SampleDataResponse,
    status_code=status.HTTP_201_CREATED,
)
def load_sample_data(t: TenantDep, _: WriterDep) -> schemas.SampleDataResponse:
    """Fill an empty organization with the reference demo dataset. Refuses once it holds any data."""
    if has_data(t.db, t.org_id):
        raise Conflict("This organization already has purchase orders or containers")
    sample = seed_sample_data(t.db, t.org)
    for c in sample.containers:
        derive_dnd(c, t.org)
    t.db.flush()
    t.db.commit()
    return schemas.SampleDataResponse(
        suppliers=sample.supplier_count,
        purchase_orders=sample.purchase_order_count,
        containers=len(sample.containers),
        costs=sample.cost_count,
        shipment_reference=sample.shipment_reference,
        container_ids=[c.id for c in sample.containers],
    )
