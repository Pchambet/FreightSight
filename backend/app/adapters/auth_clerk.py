"""Clerk JWT verification through JWKS. The only module that knows Clerk's claim layout."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient

from app.core.errors import Unauthorized

_ROLE_MAP = {"org:admin": "ADMIN", "admin": "ADMIN", "org:member": "MEMBER", "member": "MEMBER"}


@dataclass(frozen=True)
class VerifiedClaims:
    user_external_id: str
    email: str | None
    name: str | None
    org_external_id: str | None
    org_slug: str | None
    role: str  # OWNER | ADMIN | MEMBER | VIEWER


@lru_cache(maxsize=4)
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True)


class ClerkVerifier:
    def __init__(self, jwks_url: str, issuer: str, audience: str | None = None):
        self.jwks_url, self.issuer, self.audience = jwks_url, issuer, audience

    def verify(self, token: str) -> VerifiedClaims:
        try:
            key = _jwks_client(self.jwks_url).get_signing_key_from_jwt(token)
            claims: dict[str, Any] = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                issuer=self.issuer,
                audience=self.audience,
                options={"verify_aud": self.audience is not None},
                leeway=60,
            )
        except jwt.PyJWTError as e:
            raise Unauthorized(f"Invalid token: {e}") from e

        org = claims.get("o") or {}
        org_id = org.get("id") or claims.get("org_id")
        role_raw = org.get("rol") or claims.get("org_role") or "member"
        return VerifiedClaims(
            user_external_id=str(claims["sub"]),
            email=claims.get("email"),
            name=claims.get("name"),
            org_external_id=org_id,
            org_slug=org.get("slg") or claims.get("org_slug"),
            role=_ROLE_MAP.get(str(role_raw).lower(), "MEMBER"),
        )
