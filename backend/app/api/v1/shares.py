"""A landed-cost report, sent by link to somebody who has no account."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Response, status

from app.api.v1 import schemas
from app.api.v1.deps import WriterDep
from app.api.v1.landed_costs import _serialize
from app.core.auth import DbDep
from app.core.errors import NotFound
from app.core.tenancy import TenantDep, TenantSession
from app.domain.audit.service import record
from app.domain.costing import report as rpt
from app.domain.costing.service import compute
from app.domain.models import Container, PurchaseOrder, SharedReport
from app.domain.sample_registry import has_sample_data
from app.domain.shares import service as shares

router = APIRouter(tags=["shares"])


def _summaries(t: TenantSession, found: list[SharedReport]) -> list[schemas.ShareSummary]:
    names = shares.creator_names(t.db, found)
    now = datetime.now(UTC)
    out = []
    for share in found:
        summary = schemas.ShareSummary.model_validate(share)
        summary.created_by_name = names.get(share.created_by) if share.created_by else None
        summary.status = shares.status_of(share, now)  # type: ignore[assignment]
        out.append(summary)
    return out


def _share(
    t: TenantSession,
    actor: UUID | None,
    payload: schemas.ShareCreate,
    *,
    subject_type: shares.SubjectType,
    subject_id: UUID,
    label: str,
    shipment_reference: str | None,
    report: rpt.Report,
) -> schemas.ShareCreated:
    now = datetime.now(UTC)
    snapshot = {
        "issuer": {"name": t.org.name},
        "subject_type": subject_type,
        "subject_label": label,
        "shipment_reference": shipment_reference,
        "locale": t.org.locale,
        "generated_at": now.isoformat(),
        # Said on the document itself: a report sent from a demo company must not pass for a real file.
        "sample_data": has_sample_data(t.db, t.org_id),
        "report": _serialize(report).model_dump(mode="json"),
    }
    created = shares.create(
        t.db,
        t.org_id,
        subject_type=subject_type,
        subject_id=subject_id,
        subject_label=label,
        snapshot=snapshot,
        expires_in_days=payload.expires_in_days,
        created_by=actor,
    )
    record(
        t.db,
        t.org_id,
        actor_user_id=actor,
        action=f"{subject_type}.shared",
        entity_type=subject_type,
        entity_id=subject_id,
        after={"share_id": created.share.id, "expires_at": created.share.expires_at, "label": label},
    )
    t.db.commit()
    return schemas.ShareCreated(
        id=created.share.id,
        token=created.token,
        path=f"/r/{created.token}",
        expires_at=created.share.expires_at,
    )


@router.post(
    "/containers/{container_id}/share",
    response_model=schemas.ShareCreated,
    status_code=status.HTTP_201_CREATED,
)
def share_container(
    container_id: UUID, payload: schemas.ShareCreate, t: TenantDep, p: WriterDep
) -> schemas.ShareCreated:
    """Freeze this container's landed-cost report as it stands and return a link to it. The token is
    in this answer and nowhere else: only its hash is kept."""
    container = t.get_or_404(Container, container_id, "Container")
    report = rpt.container_report(compute(t.db, t.org), t.org.base_currency, container_id)
    return _share(
        t,
        p.user_id,
        payload,
        subject_type="container",
        subject_id=container_id,
        label=container.container_number,
        shipment_reference=container.shipment.reference if container.shipment else None,
        report=report,
    )


@router.post(
    "/purchase-orders/{po_id}/share", response_model=schemas.ShareCreated, status_code=status.HTTP_201_CREATED
)
def share_purchase_order(
    po_id: UUID, payload: schemas.ShareCreate, t: TenantDep, p: WriterDep
) -> schemas.ShareCreated:
    order = t.get_or_404(PurchaseOrder, po_id, "Purchase order")
    report = rpt.purchase_order_report(compute(t.db, t.org), t.org.base_currency, po_id)
    return _share(
        t,
        p.user_id,
        payload,
        subject_type="purchase_order",
        subject_id=po_id,
        label=order.po_number,
        shipment_reference=None,
        report=report,
    )


@router.get("/containers/{container_id}/shares", response_model=list[schemas.ShareSummary])
def container_shares(container_id: UUID, t: TenantDep) -> list[schemas.ShareSummary]:
    t.get_or_404(Container, container_id, "Container")
    return _summaries(t, shares.shares_of(t.db, t.org_id, "container", container_id))


@router.get("/purchase-orders/{po_id}/shares", response_model=list[schemas.ShareSummary])
def purchase_order_shares(po_id: UUID, t: TenantDep) -> list[schemas.ShareSummary]:
    t.get_or_404(PurchaseOrder, po_id, "Purchase order")
    return _summaries(t, shares.shares_of(t.db, t.org_id, "purchase_order", po_id))


@router.delete("/shares/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_share(share_id: UUID, t: TenantDep, p: WriterDep) -> None:
    """The link stops working at once. The row stays: the history of what was sent, and when."""
    share = t.get_or_404(SharedReport, share_id, "Share")
    if share.revoked_at is None:
        share.revoked_at = datetime.now(UTC)
        record(
            t.db,
            t.org_id,
            actor_user_id=p.user_id,
            action="share.revoked",
            entity_type=share.subject_type,
            entity_id=share.subject_id,
            before={"share_id": share.id, "label": share.subject_label, "view_count": share.view_count},
        )
    t.db.commit()


@router.get("/public/shared-reports/{token}", response_model=schemas.SharedReportPublic)
def open_shared_report(token: str, db: DbDep, response: Response) -> schemas.SharedReportPublic:
    """No account, no organization: the token is the whole of the right, and what it opens is the
    snapshot taken when the link was made. Unknown, expired and revoked are the same 404 — an answer
    that told them apart would tell a stranger which tokens once existed."""
    found = shares.open_by_token(db, token) if 20 <= len(token) <= 128 else None
    if found is None:
        db.rollback()
        raise NotFound("Shared report", code="SHARE_NOT_FOUND")
    snapshot, expires_at = found
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return schemas.SharedReportPublic(**snapshot, expires_at=expires_at)
