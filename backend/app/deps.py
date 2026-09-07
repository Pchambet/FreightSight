"""Request-scoped dependencies.

Phase 0 tenancy: the organization comes from an `X-Org-Id` header. This is a placeholder for the JWT-derived
org of Phase 1; it already guarantees that every query is scoped to one org.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import Organization

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[Session, Depends(get_db)]


def get_org(
    db: DbDep,
    settings: SettingsDep,
    x_org_id: Annotated[UUID | None, Header(alias="X-Org-Id")] = None,
) -> Organization:
    if x_org_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing X-Org-Id header")
    org = db.get(Organization, x_org_id)
    if org is None:
        if settings.is_prod:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
        # Dev convenience until real auth exists: create the org on first use.
        org = Organization(id=x_org_id, name="Dev organization", base_currency=settings.default_base_currency)
        db.add(org)
        db.commit()
    return org


OrgDep = Annotated[Organization, Depends(get_org)]
