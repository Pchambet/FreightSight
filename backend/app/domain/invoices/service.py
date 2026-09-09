"""The inbox: from an uploaded file to costs a person accepted.

THE RULE: no cost is ever created without a human confirming it. Everything here proposes; only
`confirm()` writes to the ledger, and it writes only what someone ticked.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Unprocessable
from app.core.money import q2, to_base
from app.domain.costing.service import recompute_org
from app.domain.documents.ports import DocumentStore
from app.domain.documents.service import store_document
from app.domain.fx.service import FxService
from app.domain.invoices.checks import check
from app.domain.invoices.ports import (
    DocumentExtractor,
    ExtractionContext,
    ExtractionFailed,
    ExtractionInput,
    ExtractorNotConfigured,
)
from app.domain.models import (
    AllocationMethod,
    Container,
    Cost,
    CostScope,
    Invoice,
    InvoiceLine,
    InvoiceStatus,
    Organization,
    PurchaseOrder,
    PurchaseOrderLine,
    Shipment,
)

logger = logging.getLogger(__name__)

SCOPE_MODEL: dict[CostScope, tuple[type, str, str]] = {
    CostScope.SHIPMENT: (Shipment, "shipment_id", "Shipment"),
    CostScope.CONTAINER: (Container, "container_id", "Container"),
    CostScope.PO: (PurchaseOrder, "po_id", "Purchase order"),
    CostScope.PO_LINE: (PurchaseOrderLine, "po_line_id", "Purchase order line"),
}


@dataclass(frozen=True)
class Confirmation:
    invoice: Invoice
    costs: list[Cost]


def create_invoice(
    db: Session,
    store: DocumentStore,
    org: Organization,
    content: bytes,
    *,
    filename: str | None,
    created_by: UUID | None = None,
) -> Invoice:
    """Store the file and open an invoice on it. Extraction happens later, in a job."""
    document = store_document(db, store, org.id, content, filename=filename, created_by=created_by)
    invoice = Invoice(
        org_id=org.id,
        document_id=document.id,
        status=InvoiceStatus.UPLOADED,
        created_by=created_by,
    )
    db.add(invoice)
    db.flush()
    return invoice


def context_for(db: Session, org: Organization) -> ExtractionContext:
    """What the extractor may know: this organization's own references, and nothing else's."""
    containers = {
        number: id_
        for number, id_ in db.execute(
            select(Container.container_number, Container.id).where(
                Container.org_id == org.id, Container.archived_at.is_(None)
            )
        ).all()
    }
    purchase_orders = {
        number: id_
        for number, id_ in db.execute(
            select(PurchaseOrder.po_number, PurchaseOrder.id).where(PurchaseOrder.org_id == org.id)
        ).all()
    }
    shipments = {
        reference: id_
        for reference, id_ in db.execute(
            select(Shipment.reference, Shipment.id).where(Shipment.org_id == org.id)
        ).all()
    }
    return ExtractionContext(
        base_currency=org.base_currency,
        containers=containers,
        purchase_orders=purchase_orders,
        shipment_references=shipments,
    )


def extract(
    db: Session,
    store: DocumentStore,
    fx: FxService,
    org: Organization,
    invoice: Invoice,
    extractors: list[DocumentExtractor],
) -> Invoice:
    """Read the document and write the proposed lines. Never raises: a failure is a status."""
    invoice.status = InvoiceStatus.EXTRACTING
    invoice.error = None
    db.flush()

    document = invoice.document
    content = store.get(org.id, document.storage_key)
    payload = ExtractionInput(content, document.content_type, document.filename)
    context = context_for(db, org)

    reading = None
    failures: list[str] = []
    for extractor in extractors:
        try:
            reading = extractor.extract(payload, context)
            invoice.extractor = extractor.name
            break
        except (ExtractionFailed, ExtractorNotConfigured) as exc:
            # The next extractor gets its turn; the reasons are kept for the one that has to fix it.
            failures.append(f"{extractor.name}: {exc.message}")
            logger.info("extractor %s could not read invoice %s: %s", extractor.name, invoice.id, exc)

    if reading is None:
        invoice.status = InvoiceStatus.FAILED
        invoice.error = " / ".join(failures) or "No extractor could read this document"
        db.flush()
        return invoice

    checked = check(
        db,
        fx,
        reading,
        context,
        base_currency=org.base_currency,
        invoice_date=reading.invoice_date,
    )
    invoice.vendor = reading.vendor
    invoice.invoice_number = reading.invoice_number
    invoice.invoice_date = reading.invoice_date
    invoice.currency = (reading.currency or org.base_currency)[:3].upper()
    invoice.total_amount = q2(Decimal(reading.total)) if reading.total else None
    invoice.vat_amount = q2(Decimal(reading.vat)) if reading.vat else None
    invoice.confidence = Decimal(str(checked.confidence))
    invoice.raw = {"reading": reading.model_dump(mode="json"), "notes": checked.notes}
    invoice.status = InvoiceStatus.NEEDS_REVIEW

    for line in list(invoice.lines):  # a retry replaces the proposal, never appends to it
        db.delete(line)
    db.flush()
    for number, proposal in enumerate(checked.lines, start=1):
        db.add(
            InvoiceLine(
                org_id=org.id,
                invoice_id=invoice.id,
                line_no=number,
                description=proposal.description,
                amount=q2(proposal.amount),
                currency=proposal.currency,
                cost_type=proposal.cost_type,
                scope=proposal.scope,
                target_id=proposal.target_id,
                confidence=Decimal(str(proposal.confidence)),
                accepted=False,  # only a person sets this
                notes="; ".join(proposal.notes) or None,
            )
        )
    db.flush()
    return invoice


def confirm(
    db: Session,
    fx: FxService,
    org: Organization,
    invoice: Invoice,
    *,
    created_by: UUID | None = None,
) -> Confirmation:
    """Turn the accepted lines into costs, all of them or none.

    Everything happens in the caller's transaction: if the tenth line is wrong, the first nine costs
    do not exist either. The rate is the one of the invoice date, fixed on the cost like any other.
    """
    if invoice.status is InvoiceStatus.CONFIRMED:
        raise Unprocessable("This invoice has already been confirmed", code="ALREADY_CONFIRMED")
    if invoice.status not in (InvoiceStatus.NEEDS_REVIEW, InvoiceStatus.FAILED):
        raise Unprocessable(
            f"An invoice can only be confirmed while it is being reviewed (this one is "
            f"{invoice.status.value})",
            code="INVALID_STATUS",
        )
    accepted = [line for line in invoice.lines if line.accepted]
    if not accepted:
        raise Unprocessable(
            "Accept at least one line before confirming: nothing is created on its own",
            code="NO_ACCEPTED_LINES",
        )

    incomplete = [
        {
            "field": f"line {line.line_no}",
            "code": "LINE_INCOMPLETE",
            "message": "an accepted line needs a cost type and a target",
        }
        for line in accepted
        if line.cost_type is None or line.scope is None or line.target_id is None
    ]
    if incomplete:
        raise Unprocessable(
            "Some accepted lines are missing a cost type or a target",
            code="LINE_INCOMPLETE",
            errors=incomplete,
        )

    cost_date = invoice.invoice_date or datetime.now(UTC).date()
    costs: list[Cost] = []
    for line in accepted:
        assert line.scope is not None and line.target_id is not None and line.cost_type is not None
        model, foreign_key, what = SCOPE_MODEL[line.scope]
        target = db.scalar(
            select(model).where(model.id == line.target_id, model.org_id == org.id)  # type: ignore[attr-defined]
        )
        if target is None:
            raise Unprocessable(
                f"{what} {line.target_id} does not belong to this organization", code="UNKNOWN_TARGET"
            )
        resolved = fx.resolve(db, org.base_currency, line.currency, cost_date)
        cost = Cost(
            org_id=org.id,
            scope=line.scope,
            cost_type=line.cost_type,
            amount=q2(line.amount),
            currency=line.currency,
            fx_rate=resolved.rate,
            fx_date=resolved.rate_date,
            fx_source=resolved.source,
            amount_base=to_base(q2(line.amount), resolved.rate),
            allocation_method=_method(org, line.cost_type),
            cost_date=cost_date,
            vendor=invoice.vendor,
            invoice_number=invoice.invoice_number,
            notes=f"From invoice {invoice.invoice_number or invoice.id} line {line.line_no}",
            created_by=created_by,
        )
        setattr(cost, foreign_key, line.target_id)
        db.add(cost)
        db.flush()
        line.cost_id = cost.id
        costs.append(cost)

    invoice.status = InvoiceStatus.CONFIRMED
    invoice.confirmed_at = datetime.now(UTC)
    db.flush()
    recompute_org(db, org)
    return Confirmation(invoice=invoice, costs=costs)


def _method(org: Organization, cost_type: object) -> AllocationMethod:
    from app.domain.models import CostType

    if cost_type is CostType.CUSTOMS_DUTY:
        return AllocationMethod.BY_CIF_VALUE
    return org.default_allocation_method
