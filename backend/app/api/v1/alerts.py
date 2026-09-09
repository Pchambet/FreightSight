"""Alerts: what happened while nobody was looking."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query

from app.api.v1 import schemas
from app.core.errors import NotFound
from app.core.tenancy import TenantDep
from app.domain.alerts.service import mark_all_read, mark_read, unread_count
from app.domain.models import Alert

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[schemas.AlertResponse])
def list_alerts(
    t: TenantDep,
    unread: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[schemas.AlertResponse]:
    stmt = t.q(Alert).order_by(Alert.created_at.desc()).limit(limit)
    if unread:
        stmt = stmt.where(Alert.read_at.is_(None))
    return [schemas.AlertResponse.model_validate(a) for a in t.db.scalars(stmt)]


@router.post("/{alert_id}/read", response_model=schemas.AlertResponse)
def read_alert(alert_id: UUID, t: TenantDep) -> schemas.AlertResponse:
    alert = mark_read(t.db, t.org_id, alert_id)
    if alert is None:
        raise NotFound("Alert")
    t.db.commit()
    return schemas.AlertResponse.model_validate(alert)


@router.post("/read-all", response_model=schemas.AlertsRead)
def read_all_alerts(t: TenantDep) -> schemas.AlertsRead:
    marked = mark_all_read(t.db, t.org_id)
    t.db.commit()
    return schemas.AlertsRead(marked=marked)


@router.get("/count", response_model=schemas.AlertsRead)
def count_unread(t: TenantDep) -> schemas.AlertsRead:
    """The number behind the bell, for clients that want it without the list."""
    return schemas.AlertsRead(marked=unread_count(t.db, t.org_id))
