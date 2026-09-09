"""Reading the audit log. Nothing here writes: the log is append-only in the database itself."""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import literal, tuple_

from app.api.v1 import schemas
from app.core.errors import Unprocessable
from app.core.tenancy import TenantDep
from app.domain.models import AuditLog

router = APIRouter(prefix="/audit-log", tags=["audit"])


def encode_cursor(entry: AuditLog) -> str:
    """`(at, id)` — the timestamp alone is not unique, and two entries can share a millisecond."""
    raw = f"{entry.at.isoformat()}|{entry.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        at, entry_id = base64.urlsafe_b64decode(cursor.encode()).decode().split("|", 1)
        return datetime.fromisoformat(at), UUID(entry_id)
    except (ValueError, binascii.Error) as exc:
        raise Unprocessable("This cursor is not one of ours", code="INVALID_CURSOR") from exc


@router.get("", response_model=schemas.AuditPage)
def list_audit_log(
    t: TenantDep,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    action: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> schemas.AuditPage:
    """History, newest first, paginated by cursor.

    A cursor rather than an offset because the log grows while it is being read: with an offset, an
    entry written between two pages shifts everything and something is silently skipped.
    """
    stmt = t.q(AuditLog).order_by(AuditLog.at.desc(), AuditLog.id.desc()).limit(limit + 1)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if cursor:
        at, entry_id = decode_cursor(cursor)
        # Row-value comparison: "older than this instant, or the same instant and a smaller id".
        stmt = stmt.where(tuple_(AuditLog.at, AuditLog.id) < tuple_(literal(at), literal(entry_id)))

    rows = list(t.db.scalars(stmt))
    has_more = len(rows) > limit
    page = rows[:limit]
    return schemas.AuditPage(
        entries=[schemas.AuditEntryResponse.model_validate(row) for row in page],
        next_cursor=encode_cursor(page[-1]) if has_more and page else None,
    )
