from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, status

from app.api.v1 import schemas
from app.api.v1.deps import WriterDep
from app.core.auth import PrincipalDep
from app.core.errors import Conflict, Unprocessable
from app.core.tenancy import TenantDep
from app.domain.alerts.service import raise_dnd_risk_alert, unread_count
from app.domain.audit.service import ORGANIZATION_UPDATED, record
from app.domain.costing.service import recompute_org
from app.domain.sample_data import has_data, seed_sample_data
from app.domain.tracking.registry import provider_names
from app.domain.tracking.state import derive_dnd

router = APIRouter(tags=["organization"])


@router.get("/me", response_model=schemas.MeResponse)
def me(p: PrincipalDep) -> schemas.MeResponse:
    return schemas.MeResponse(org_id=p.org_id, user_id=p.user_id, role=p.role, via=p.via)


def _check_settings(settings: dict[str, object] | None) -> None:
    """A default tracking provider we do not have is a setting that fails at the worst moment: when
    someone finally clicks "track this container"."""
    if not settings:
        return
    chosen = settings.get("tracking_provider_default")
    if chosen is not None and (not isinstance(chosen, str) or chosen not in provider_names()):
        raise Unprocessable(
            f"tracking_provider_default must be one of: {', '.join(provider_names())}",
            code="UNKNOWN_PROVIDER",
        )


def _organization(t: TenantDep) -> schemas.OrganizationResponse:
    response = schemas.OrganizationResponse.model_validate(t.org)
    response.unread_alerts = unread_count(t.db, t.org_id)
    return response


@router.get("/organization", response_model=schemas.OrganizationResponse)
def get_organization(t: TenantDep) -> schemas.OrganizationResponse:
    return _organization(t)


@router.patch("/organization", response_model=schemas.OrganizationResponse)
def update_organization(
    payload: schemas.OrganizationUpdate, t: TenantDep, p: PrincipalDep, _: WriterDep
) -> schemas.OrganizationResponse:
    changes = payload.model_dump(exclude_unset=True)
    _check_settings(changes.get("settings"))
    before = {k: getattr(t.org, k) for k in changes}
    for k, v in changes.items():
        setattr(t.org, k, v)
    record(
        t.db,
        t.org_id,
        actor_user_id=p.user_id,
        action=ORGANIZATION_UPDATED,
        entity_type="organization",
        entity_id=t.org_id,
        before=before,
        after=changes,
    )
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
    now = datetime.now(UTC)
    for c in sample.containers:
        derive_dnd(c, t.org, now)
        raise_dnd_risk_alert(t.db, t.org, c, now)
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
