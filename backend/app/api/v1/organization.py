from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import schemas
from app.api.v1.deps import WriterDep
from app.core.auth import PrincipalDep
from app.core.tenancy import TenantDep
from app.domain.costing.service import recompute_org
from app.domain.models import Organization

router = APIRouter(tags=["organization"])


@router.get("/me", response_model=schemas.MeResponse)
def me(p: PrincipalDep) -> schemas.MeResponse:
    return schemas.MeResponse(org_id=p.org_id, user_id=p.user_id, role=p.role, via=p.via)


@router.get("/organization", response_model=schemas.OrganizationResponse)
def get_organization(t: TenantDep) -> Organization:
    return t.org


@router.patch("/organization", response_model=schemas.OrganizationResponse)
def update_organization(payload: schemas.OrganizationUpdate, t: TenantDep, _: WriterDep) -> Organization:
    changes = payload.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(t.org, k, v)
    if "default_allocation_method" in changes:
        recompute_org(t.db, t.org)
    t.db.commit()
    t.db.refresh(t.org)
    return t.org
