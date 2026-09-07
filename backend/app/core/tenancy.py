"""Tenant-scoped data access: belt (application filter) and braces (Postgres Row Level Security)."""

from __future__ import annotations

from typing import Annotated, TypeVar
from uuid import UUID

from fastapi import Depends
from sqlalchemy import Select, select, text
from sqlalchemy.orm import Session

from app.core.auth import DbDep, Principal, PrincipalDep
from app.core.errors import NotFound, TenantViolation
from app.domain.models import Organization

T = TypeVar("T")

# Postgres session variable read by every RLS policy. Set per request, reset when the pooled
# connection is returned (see app.core.db / main lifespan).
ORG_GUC = "app.org_id"


def set_current_org(db: Session, org_id: UUID | None) -> None:
    db.execute(text(f"SELECT set_config('{ORG_GUC}', :v, false)"), {"v": str(org_id) if org_id else ""})


class TenantSession:
    def __init__(self, db: Session, principal: Principal, org: Organization):
        self.db = db
        self.principal = principal
        self.org = org
        self.org_id = org.id

    def q(self, model: type[T]) -> Select[tuple[T]]:
        return select(model).where(model.org_id == self.org_id)  # type: ignore[attr-defined]

    def get_or_404(self, model: type[T], id: UUID, what: str | None = None) -> T:
        obj = self.db.scalar(self.q(model).where(model.id == id))  # type: ignore[attr-defined]
        if obj is None:
            raise NotFound(what or model.__name__)
        return obj

    def add(self, obj: T) -> T:
        current = getattr(obj, "org_id", None)
        if current not in (None, self.org_id):
            raise TenantViolation("Object belongs to another organization")
        obj.org_id = self.org_id  # type: ignore[attr-defined]
        self.db.add(obj)
        return obj


def get_tenant(db: DbDep, principal: PrincipalDep) -> TenantSession:
    set_current_org(db, principal.org_id)
    org = db.get(Organization, principal.org_id)
    if org is None:
        raise NotFound("Organization")
    return TenantSession(db, principal, org)


TenantDep = Annotated[TenantSession, Depends(get_tenant)]
