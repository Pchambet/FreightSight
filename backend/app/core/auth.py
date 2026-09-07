"""Who is calling, and for which organization.

Order of resolution:
1. `Authorization: Bearer <Clerk JWT>` when Clerk is configured: verified via JWKS, user/org/membership
   mirrored locally (the local membership is what authorises).
2. Outside prod, `X-Org-Id` (+ optional `X-User-Email`) as a development principal with role OWNER.
3. Otherwise 401.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import Forbidden, Unauthorized
from app.core.settings import Settings, get_settings
from app.domain.models import MemberRole, Membership, Organization, User

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[Session, Depends(get_db)]


@dataclass(frozen=True)
class Principal:
    org_id: UUID
    user_id: UUID | None
    role: MemberRole
    via: Literal["jwt", "dev"]


def _verifier(settings: Settings):  # type: ignore[no-untyped-def]
    from app.adapters.auth_clerk import ClerkVerifier

    assert settings.clerk_jwks_url and settings.clerk_issuer
    return ClerkVerifier(settings.clerk_jwks_url, settings.clerk_issuer, settings.clerk_audience)


def _principal_from_jwt(db: Session, settings: Settings, token: str) -> Principal:
    claims = _verifier(settings).verify(token)
    if not claims.org_external_id:
        raise Forbidden("Select an organization first")

    user = db.scalar(select(User).where(User.external_id == claims.user_external_id))
    if user is None:
        user = User(external_id=claims.user_external_id, email=claims.email or "", name=claims.name)
        db.add(user)
    else:
        user.email = claims.email or user.email
        user.name = claims.name or user.name

    org = db.scalar(select(Organization).where(Organization.external_id == claims.org_external_id))
    if org is None:
        org = Organization(
            name=claims.org_slug or "New organization",
            slug=claims.org_slug,
            external_id=claims.org_external_id,
            base_currency=settings.default_base_currency,
        )
        db.add(org)
    db.flush()

    membership = db.get(Membership, (org.id, user.id))
    role = MemberRole(claims.role)
    if membership is None:
        membership = Membership(org_id=org.id, user_id=user.id, role=role)
        db.add(membership)
    elif membership.role != role and membership.role != MemberRole.OWNER:
        membership.role = role
    db.commit()
    return Principal(org_id=org.id, user_id=user.id, role=membership.role, via="jwt")


def _principal_from_dev_header(db: Session, settings: Settings, org_id: UUID) -> Principal:
    org = db.get(Organization, org_id)
    if org is None:
        org = Organization(id=org_id, name="Dev organization", base_currency=settings.default_base_currency)
        db.add(org)
        db.commit()
    return Principal(org_id=org.id, user_id=None, role=MemberRole.OWNER, via="dev")


def get_principal(
    request: Request,
    db: DbDep,
    settings: SettingsDep,
    x_org_id: Annotated[UUID | None, Header(alias="X-Org-Id")] = None,
) -> Principal:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer ") and settings.clerk_enabled:
        return _principal_from_jwt(db, settings, auth[7:].strip())
    if x_org_id is not None and not settings.is_prod:
        return _principal_from_dev_header(db, settings, x_org_id)
    if auth.lower().startswith("bearer "):
        raise Unauthorized("Authentication is not configured on this server")
    raise Unauthorized("Missing credentials")


PrincipalDep = Annotated[Principal, Depends(get_principal)]


def require_role(*roles: MemberRole):  # type: ignore[no-untyped-def]
    def dep(p: PrincipalDep) -> Principal:
        if p.role not in roles:
            raise Forbidden(f"Requires one of: {', '.join(r.value for r in roles)}")
        return p

    return dep


WRITE_ROLES = (MemberRole.OWNER, MemberRole.ADMIN, MemberRole.MEMBER)
