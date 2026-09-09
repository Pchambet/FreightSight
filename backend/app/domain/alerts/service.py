"""Raising alerts, without raising the same one twice.

Everything an alert says has to survive being recomputed: the daily demurrage pass looks at the same
container every morning, and the ETA job re-reads the same history rows. `dedup_key` carries that —
one row per organization per key — so a job can be written as "state the fact" rather than "work out
whether I already said this".
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.domain.models import Alert, AlertKind, AlertSeverity

logger = logging.getLogger(__name__)


def raise_alert(
    db: Session,
    org_id: UUID,
    *,
    kind: AlertKind,
    severity: AlertSeverity,
    title: str,
    body: str = "",
    dedup_key: str,
    container_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> Alert | None:
    """Create the alert, or return None because this organization has already been told."""
    stmt = (
        insert(Alert)
        .values(
            org_id=org_id,
            container_id=container_id,
            kind=kind,
            severity=severity,
            title=title,
            body=body,
            dedup_key=dedup_key,
            payload=payload or {},
            created_at=datetime.now(UTC),
        )
        .on_conflict_do_nothing(index_elements=["org_id", "dedup_key"])
        .returning(Alert)
    )
    alert = db.scalars(stmt).one_or_none()
    db.flush()
    if alert is not None:
        logger.info("alert %s raised for org %s: %s", kind.value, org_id, title)
    return alert


def unread_count(db: Session, org_id: UUID) -> int:
    return db.scalar(select(func.count(Alert.id)).where(Alert.org_id == org_id, Alert.read_at.is_(None))) or 0


def mark_read(db: Session, org_id: UUID, alert_id: UUID) -> Alert | None:
    alert = db.scalar(select(Alert).where(Alert.org_id == org_id, Alert.id == alert_id))
    if alert is None:
        return None
    if alert.read_at is None:
        alert.read_at = datetime.now(UTC)
        db.flush()
    return alert


def mark_all_read(db: Session, org_id: UUID) -> int:
    now = datetime.now(UTC)
    alerts = list(db.scalars(select(Alert).where(Alert.org_id == org_id, Alert.read_at.is_(None))))
    for alert in alerts:
        alert.read_at = now
    db.flush()
    return len(alerts)
