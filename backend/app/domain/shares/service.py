"""Sharing a landed-cost report with somebody who has no account.

Two things make it safe to hand out. The link is a random 256-bit token of which only the SHA-256 is
stored: the database cannot be read back into links. And what the link opens is a **snapshot**, taken
when it was created: it cannot be used to watch a company's figures move, and the person it was sent
to sees the number they were sent.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.domain.models import SharedReport, User

SubjectType = Literal["container", "purchase_order"]
#: The setting the token policy of `shared_reports` reads (migration 0025).
TOKEN_GUC = "app.share_token_hash"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class Created:
    share: SharedReport
    #: Shown once, to whoever created the link, and never stored.
    token: str


def create(
    db: Session,
    org_id: UUID,
    *,
    subject_type: SubjectType,
    subject_id: UUID,
    subject_label: str,
    snapshot: dict[str, Any],
    expires_in_days: int,
    created_by: UUID | None,
) -> Created:
    token = secrets.token_urlsafe(32)
    share = SharedReport(
        org_id=org_id,
        subject_type=subject_type,
        subject_id=subject_id,
        subject_label=subject_label,
        token_hash=hash_token(token),
        snapshot=snapshot,
        created_by=created_by,
        expires_at=datetime.now(UTC) + timedelta(days=expires_in_days),
    )
    db.add(share)
    db.flush()
    return Created(share, token)


def status_of(share: SharedReport, now: datetime | None = None) -> str:
    if share.revoked_at is not None:
        return "revoked"
    return "expired" if share.expires_at <= (now or datetime.now(UTC)) else "active"


def shares_of(db: Session, org_id: UUID, subject_type: SubjectType, subject_id: UUID) -> list[SharedReport]:
    return list(
        db.scalars(
            select(SharedReport)
            .where(
                SharedReport.org_id == org_id,
                SharedReport.subject_type == subject_type,
                SharedReport.subject_id == subject_id,
            )
            .order_by(SharedReport.created_at.desc())
        )
    )


def creator_names(db: Session, shares: list[SharedReport]) -> dict[UUID, str]:
    ids = {s.created_by for s in shares if s.created_by}
    if not ids:
        return {}
    rows = db.execute(select(User.id, User.name, User.email).where(User.id.in_(ids)))
    return {user_id: name or email for user_id, name, email in rows}


def open_by_token(db: Session, token: str) -> tuple[dict[str, Any], datetime] | None:
    """The snapshot behind a token, counted as opened — or None for a token that is unknown, expired
    or revoked, which are one and the same answer to whoever is asking.

    There is no tenant here. The row is reached through the token policy of the table: the hash is set
    for this transaction only, and the policy lets through the row that carries it, and no other.
    """
    hashed = hash_token(token)
    db.execute(text(f"SELECT set_config('{TOKEN_GUC}', :h, true)"), {"h": hashed})
    row = db.execute(
        text(
            "UPDATE shared_reports SET view_count = view_count + 1, last_viewed_at = now() "
            "WHERE token_hash = :h AND revoked_at IS NULL AND expires_at > now() "
            "RETURNING snapshot, expires_at"
        ),
        {"h": hashed},
    ).one_or_none()
    db.execute(text(f"SELECT set_config('{TOKEN_GUC}', '', true)"))
    if row is None:
        return None
    return row[0], row[1]
