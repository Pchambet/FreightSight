"""Connecting an organization's ERP, and reading its purchase orders.

Read-only: this brick imports orders, it writes nothing back into the customer's system.
"""

from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.v1 import schemas
from app.api.v1.deps import WriterDep
from app.core.crypto import CryptoError
from app.core.errors import Conflict, NotFound, Unprocessable
from app.core.tenancy import TenantDep
from app.domain.erp import service
from app.domain.models import ErpConnection, ErpSyncRun

router = APIRouter(prefix="/erp", tags=["erp"])


@router.get("/connection", response_model=schemas.ErpConnectionResponse)
def get_connection(t: TenantDep) -> ErpConnection:
    connection = service.connection_for(t.db, t.org_id)
    if connection is None:
        raise NotFound("ERP connection")
    return connection


@router.post("/connection", response_model=schemas.ErpConnectionResponse, status_code=status.HTTP_201_CREATED)
def create_connection(payload: schemas.ErpConnectionCreate, t: TenantDep, p: WriterDep) -> ErpConnection:
    """Store the connection — after proving it works.

    The test happens before anything is written: a saved connection that has never authenticated is
    a promise the next sync will break, and the error the ERP gives is far more useful now, while
    the person who typed the credentials is still looking at them.
    """
    if service.connection_for(t.db, t.org_id) is not None:
        raise Conflict("This organization already has an ERP connection", code="ERP_ALREADY_CONNECTED")
    try:
        sealed = service.seal_key(payload.api_key)
    except CryptoError as exc:
        raise Unprocessable(
            f"This deployment cannot store ERP credentials: {exc}", code="ERP_KEY_MISSING"
        ) from exc

    connection = ErpConnection(
        org_id=t.org_id,
        kind=payload.kind,
        url=payload.url,
        database=payload.database,
        login=payload.login,
        api_key_sealed=sealed,
        created_by=p.user_id,
    )
    identity = service.connector_for(connection).test_connection()
    connection.server_version = identity.server_version
    connection.company = identity.company
    t.add(connection)
    t.db.commit()
    t.db.refresh(connection)
    return connection


@router.delete("/connection", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(t: TenantDep, _: WriterDep) -> None:
    """Forget the ERP. The orders already imported stay: they are ours now."""
    connection = service.connection_for(t.db, t.org_id)
    if connection is None:
        raise NotFound("ERP connection")
    t.db.delete(connection)
    t.db.commit()


@router.post("/sync", response_model=schemas.ErpSyncRunResponse, status_code=status.HTTP_202_ACCEPTED)
def sync_now(t: TenantDep, _: WriterDep, full: bool = False) -> ErpSyncRun:
    """Read the ERP now, in this request.

    Deliberately synchronous: someone has just connected their Odoo and is watching this button.
    The daily refresh is the job; this is the reassurance. `full=true` re-reads the whole history
    instead of what has changed — the button for "this looks wrong, start again".
    """
    connection = service.connection_for(t.db, t.org_id)
    if connection is None:
        raise NotFound("ERP connection")
    try:
        result = service.sync(t, connection, full=full)
    except Exception:
        # The run row was written before the failure and says why; keep it and let the error surface.
        t.db.commit()
        raise
    t.db.commit()
    t.db.refresh(result.run)
    return result.run


@router.get("/sync-runs", response_model=list[schemas.ErpSyncRunResponse])
def list_sync_runs(t: TenantDep, limit: int = 20) -> list[ErpSyncRun]:
    return list(
        t.db.scalars(
            select(ErpSyncRun)
            .where(ErpSyncRun.org_id == t.org_id)
            .order_by(ErpSyncRun.started_at.desc())
            .limit(min(limit, 100))
        )
    )
