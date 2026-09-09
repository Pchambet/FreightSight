"""Reading a supplier invoice.

THE RULE, and it holds everywhere below this line: **no cost is ever created without a human
confirming it.** Extraction proposes; a person accepts, line by line, and only then does
`POST /invoices/{id}/confirm` write anything into the ledger. A confident extractor and a careless
one differ in how much typing they save, never in what reaches the accounts.

Amounts cross this boundary as strings. A float would already have lost the cents by the time anyone
looked, and the extractor is exactly where a wrong 0.01 is easiest to introduce and hardest to see.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.errors import DomainError
from app.domain.models import CostType


class ExtractionFailed(DomainError):
    status = 422
    code = "EXTRACTION_FAILED"


class ExtractorNotConfigured(DomainError):
    status = 501
    code = "EXTRACTOR_NOT_CONFIGURED"


class ExtractedLine(BaseModel):
    """One charge on the invoice, as read. `amount` is a decimal string, never a float."""

    description: str = ""
    amount: str
    currency: str | None = None
    cost_type: CostType | None = None
    container_number: str | None = None
    po_number: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    def decimal(self) -> Decimal | None:
        try:
            return Decimal(self.amount)
        except (InvalidOperation, ValueError):
            return None


class FreightInvoice(BaseModel):
    """What an extractor claims to have read. Nothing here is trusted enough to become a cost."""

    vendor: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    currency: str | None = None
    total: str | None = None
    vat: str | None = None
    lines: list[ExtractedLine] = Field(default_factory=list)
    container_numbers: list[str] = Field(default_factory=list)
    bl_numbers: list[str] = Field(default_factory=list)
    po_numbers: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class ExtractionContext:
    """What the extractor is allowed to know about this organization.

    The container and PO lists are given to the model so that it *recognises* references instead of
    inventing them: anything it returns that is not in these lists is dropped downstream.
    """

    base_currency: str
    containers: dict[str, UUID] = field(default_factory=dict)  # container number -> id
    purchase_orders: dict[str, UUID] = field(default_factory=dict)  # PO number -> id
    shipment_references: dict[str, UUID] = field(default_factory=dict)


@dataclass(frozen=True)
class ExtractionInput:
    content: bytes
    content_type: str
    filename: str | None = None


@runtime_checkable
class DocumentExtractor(Protocol):
    name: str

    def extract(self, document: ExtractionInput, context: ExtractionContext) -> FreightInvoice:
        """Read the document, or raise `ExtractionFailed` with a reason a human can act on."""
        ...
