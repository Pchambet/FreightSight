"""The invoice inbox.

THE RULE: no cost is created without a human confirming it. Upload and extraction only ever propose;
`POST /invoices/{id}/confirm` is the single place in this application where an invoice becomes money
in the ledger, and it writes only the lines somebody accepted.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, File, Response, UploadFile, status
from sqlalchemy.orm import selectinload

from app.api.v1 import schemas
from app.api.v1.deps import FxDep, WriterDep
from app.core.errors import NotFound
from app.core.tenancy import TenantDep, TenantSession
from app.domain.audit.service import INVOICE_CONFIRMED, INVOICE_REJECTED, record
from app.domain.documents.registry import get_store
from app.domain.invoices.service import confirm as confirm_invoice
from app.domain.invoices.service import create_invoice
from app.domain.models import Invoice, InvoiceStatus
from app.jobs.app import defer

router = APIRouter(prefix="/invoices", tags=["invoices"])


def _get(t: TenantSession, invoice_id: UUID) -> Invoice:
    invoice = t.db.scalar(
        t.q(Invoice)
        .where(Invoice.id == invoice_id)
        .options(selectinload(Invoice.lines), selectinload(Invoice.document))
    )
    if invoice is None:
        raise NotFound("Invoice")
    return invoice


def _response(invoice: Invoice) -> schemas.InvoiceResponse:
    summary = schemas.InvoiceSummary.model_validate(invoice).model_dump()
    summary["filename"] = invoice.document.filename if invoice.document else None
    return schemas.InvoiceResponse(
        **summary,
        lines=[schemas.InvoiceLineResponse.model_validate(ln) for ln in invoice.lines],
        # The route, not a storage URL: the bytes always come back through this API.
        document_url=f"/api/v1/invoices/{invoice.id}/document",
        notes=list(invoice.raw.get("notes", [])) if isinstance(invoice.raw, dict) else [],
    )


@router.post("", response_model=schemas.InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def upload_invoice(t: TenantDep, p: WriterDep, file: UploadFile = File(...)) -> schemas.InvoiceResponse:
    """Accept a file and open an invoice on it. Reading happens in a job; this answers immediately.

    The extraction job is deferred inside this transaction: if the upload rolls back, the job never
    existed either.
    """
    content = await file.read()
    invoice = create_invoice(
        t.db,
        get_store(t.db),
        t.org,
        content,
        filename=file.filename,
        created_by=p.user_id,
    )
    from app.jobs.tasks import extract_invoice

    defer(
        t.db,
        extract_invoice,
        lock=f"invoice:{invoice.id}",
        org_id=str(t.org_id),
        invoice_id=str(invoice.id),
    )
    t.db.commit()
    t.db.refresh(invoice)
    return _response(invoice)


@router.get("", response_model=list[schemas.InvoiceSummary])
def list_invoices(t: TenantDep, invoice_status: InvoiceStatus | None = None) -> list[schemas.InvoiceSummary]:
    stmt = t.q(Invoice).options(selectinload(Invoice.document)).order_by(Invoice.created_at.desc())
    if invoice_status:
        stmt = stmt.where(Invoice.status == invoice_status)
    out = []
    for invoice in t.db.scalars(stmt):
        summary = schemas.InvoiceSummary.model_validate(invoice)
        summary.filename = invoice.document.filename if invoice.document else None
        out.append(summary)
    return out


@router.get("/{invoice_id}", response_model=schemas.InvoiceResponse)
def get_invoice(invoice_id: UUID, t: TenantDep) -> schemas.InvoiceResponse:
    return _response(_get(t, invoice_id))


@router.get("/{invoice_id}/document")
def get_invoice_document(invoice_id: UUID, t: TenantDep) -> Response:
    """The file itself, streamed by the API.

    Never a storage URL: a document stays behind the same authentication and the same tenancy checks
    as its metadata, wherever its bytes happen to live.
    """
    invoice = _get(t, invoice_id)
    content = get_store(t.db).get(t.org_id, invoice.document.storage_key)
    filename = invoice.document.filename or f"invoice-{invoice.id}"
    return Response(
        content=content,
        media_type=invoice.document.content_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.patch("/{invoice_id}/lines/{line_id}", response_model=schemas.InvoiceResponse)
def update_line(
    invoice_id: UUID,
    line_id: UUID,
    payload: schemas.InvoiceLineUpdate,
    t: TenantDep,
    _: WriterDep,
) -> schemas.InvoiceResponse:
    """Correct what was read, and accept the line or not. This is the human half of the loop."""
    invoice = _get(t, invoice_id)
    if invoice.status is InvoiceStatus.CONFIRMED:
        raise NotFound("Invoice line")  # a confirmed invoice is history, not a draft
    line = next((ln for ln in invoice.lines if ln.id == line_id), None)
    if line is None:
        raise NotFound("Invoice line")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(line, field, value)
    t.db.flush()
    t.db.commit()
    t.db.refresh(invoice)
    return _response(invoice)


@router.post("/{invoice_id}/confirm", response_model=schemas.InvoiceConfirmResponse)
def confirm(invoice_id: UUID, t: TenantDep, fx: FxDep, p: WriterDep) -> schemas.InvoiceConfirmResponse:
    """Create the accepted lines as costs — all of them, or none of them.

    One transaction: the costs, the invoice's new status and the recomputed allocations land
    together. A line pointing at something that is not ours stops the whole confirmation.
    """
    invoice = _get(t, invoice_id)
    try:
        result = confirm_invoice(t.db, fx, t.org, invoice, created_by=p.user_id)
    except Exception:
        # All or nothing, said out loud: a refusal halfway through leaves no half-written costs
        # behind, not even for the rest of this session.
        t.db.rollback()
        raise
    record(
        t.db,
        t.org_id,
        actor_user_id=p.user_id,
        action=INVOICE_CONFIRMED,
        entity_type="invoice",
        entity_id=invoice.id,
        after={
            "invoice_number": invoice.invoice_number,
            "vendor": invoice.vendor,
            "cost_ids": [c.id for c in result.costs],
            "total_amount": invoice.total_amount,
        },
    )
    t.db.commit()
    t.db.refresh(invoice)
    return schemas.InvoiceConfirmResponse(
        invoice=_response(invoice),
        costs_created=len(result.costs),
        cost_ids=[c.id for c in result.costs],
        superseded_estimate_ids=result.superseded,
        notes=result.notes,
    )


@router.post("/{invoice_id}/reject", response_model=schemas.InvoiceResponse)
def reject(invoice_id: UUID, t: TenantDep, p: WriterDep) -> schemas.InvoiceResponse:
    """Not our invoice, a duplicate, an error: it stays on file, it creates nothing."""
    invoice = _get(t, invoice_id)
    if invoice.status is InvoiceStatus.CONFIRMED:
        raise NotFound("Invoice")  # confirmed costs are undone by deleting the costs, not the invoice
    before = {"status": invoice.status}
    invoice.status = InvoiceStatus.REJECTED
    record(
        t.db,
        t.org_id,
        actor_user_id=p.user_id,
        action=INVOICE_REJECTED,
        entity_type="invoice",
        entity_id=invoice.id,
        before=before,
        after={"status": invoice.status},
    )
    t.db.commit()
    t.db.refresh(invoice)
    return _response(invoice)


@router.post("/{invoice_id}/retry", response_model=schemas.InvoiceResponse)
def retry(invoice_id: UUID, t: TenantDep, _: WriterDep) -> schemas.InvoiceResponse:
    """Read the document again — after a fix on our side, or once a model key exists."""
    invoice = _get(t, invoice_id)
    if invoice.status is InvoiceStatus.CONFIRMED:
        raise NotFound("Invoice")
    invoice.status = InvoiceStatus.UPLOADED
    invoice.error = None
    t.db.flush()
    from app.jobs.tasks import extract_invoice

    defer(
        t.db,
        extract_invoice,
        lock=f"invoice:{invoice.id}",
        org_id=str(t.org_id),
        invoice_id=str(invoice.id),
    )
    t.db.commit()
    t.db.refresh(invoice)
    return _response(invoice)
