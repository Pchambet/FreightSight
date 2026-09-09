"""API v1 schemas. Money and quantities are Decimal in, strings out. Never float."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator, model_validator

from app.domain.models import (
    AlertKind,
    AlertSeverity,
    AllocationMethod,
    ContainerMilestone,
    CostScope,
    CostStatus,
    CostType,
    DndRisk,
    ImportKind,
    ImportStatus,
    Incoterm,
    InvoiceStatus,
    MemberRole,
    MilestoneCode,
    RateBasis,
    TrackingState,
)

Money = Annotated[Decimal, PlainSerializer(lambda d: f"{d:.2f}", return_type=str, when_used="json")]
Qty = Annotated[Decimal, PlainSerializer(lambda d: f"{d:.4f}", return_type=str, when_used="json")]
Rate = Annotated[
    Decimal, PlainSerializer(lambda d: f"{d:.8f}".rstrip("0").rstrip("."), return_type=str, when_used="json")
]
Pct = Annotated[Decimal, PlainSerializer(lambda d: f"{d:.2f}", return_type=str, when_used="json")]


def currency_code(v: str) -> str:
    v = v.strip().upper()
    if len(v) != 3 or not v.isalpha():
        raise ValueError("currency must be a 3-letter ISO code")
    return v


class Problem(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    code: str | None = None
    detail: str | None = None
    errors: list[dict[str, str]] | None = None
    #: The id of the request that produced this error, also in the X-Request-ID response header.
    request_id: str | None = None


# ---------------------------------------------------------------------------- identity


class MeResponse(BaseModel):
    org_id: UUID
    user_id: UUID | None
    role: MemberRole
    via: str


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    slug: str | None
    base_currency: str
    default_allocation_method: AllocationMethod
    default_incoterm: Incoterm | None
    free_days_demurrage: int
    free_days_detention: int
    settings: dict[str, Any]
    unread_alerts: int = 0  # what the bell shows


class SampleDataResponse(BaseModel):
    """What POST /organization/sample-data created."""

    suppliers: int
    purchase_orders: int
    containers: int
    costs: int
    shipment_reference: str
    container_ids: list[UUID]


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    base_currency: str | None = None
    default_allocation_method: AllocationMethod | None = None
    default_incoterm: Incoterm | None = None
    free_days_demurrage: int | None = Field(default=None, ge=0, le=60)
    free_days_detention: int | None = Field(default=None, ge=0, le=60)
    settings: dict[str, Any] | None = None

    @field_validator("base_currency")
    @classmethod
    def _cur(cls, v: str | None) -> str | None:
        return None if v is None else currency_code(v)

    @field_validator("default_allocation_method")
    @classmethod
    def _method(cls, v: AllocationMethod | None) -> AllocationMethod | None:
        if v in (
            AllocationMethod.MANUAL,
            AllocationMethod.BY_CIF_VALUE,
            AllocationMethod.BY_THEORETICAL_DUTY,
        ):
            raise ValueError("default method must be BY_VALUE, BY_WEIGHT, BY_VOLUME or BY_QUANTITY")
        return v


# ---------------------------------------------------------------------------- suppliers


class SupplierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    default_currency: str | None = None

    @field_validator("default_currency")
    @classmethod
    def _cur(cls, v: str | None) -> str | None:
        return None if v is None else currency_code(v)


class SupplierUpdate(SupplierCreate):
    name: str | None = Field(default=None, min_length=1, max_length=200)  # type: ignore[assignment]


class SupplierResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    country: str | None
    default_currency: str | None


# ---------------------------------------------------------------------------- purchase orders


class PoLineIn(BaseModel):
    line_no: int = Field(ge=1)
    sku: str | None = None
    description: str | None = None
    hs_code: str | None = None
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=4)
    unit_price: Decimal = Field(ge=0, max_digits=14, decimal_places=4)
    unit_weight_kg: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=4)
    unit_volume_cbm: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=6)
    duty_rate: Decimal | None = Field(default=None, ge=0, le=5, max_digits=7, decimal_places=4)


class PoLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    line_no: int
    sku: str | None
    description: str | None
    hs_code: str | None
    quantity: Qty
    unit_price: Qty
    unit_weight_kg: Qty | None
    unit_volume_cbm: Qty | None
    duty_rate: Rate | None


class PurchaseOrderCreate(BaseModel):
    po_number: str = Field(min_length=1, max_length=64)
    supplier_id: UUID | None = None
    currency: str | None = None
    fx_rate: Decimal | None = Field(default=None, gt=0)
    fx_date: date | None = None
    incoterm: Incoterm | None = None
    order_date: date | None = None
    lines: list[PoLineIn] = Field(default_factory=list)

    @field_validator("currency")
    @classmethod
    def _cur(cls, v: str | None) -> str | None:
        return None if v is None else currency_code(v)

    @model_validator(mode="after")
    def _unique_lines(self) -> PurchaseOrderCreate:
        nos = [ln.line_no for ln in self.lines]
        if len(nos) != len(set(nos)):
            raise ValueError("line_no must be unique within a purchase order")
        return self


class PurchaseOrderUpdate(BaseModel):
    supplier_id: UUID | None = None
    fx_rate: Decimal | None = Field(default=None, gt=0)
    fx_date: date | None = None
    incoterm: Incoterm | None = None
    order_date: date | None = None
    lines: list[PoLineIn] | None = None  # upsert by line_no; lines absent from the list are kept


class PurchaseOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    po_number: str
    supplier_id: UUID | None
    supplier_name: str | None = None
    currency: str
    fx_rate: Rate
    fx_date: date | None
    incoterm: Incoterm | None
    order_date: date | None
    lines: list[PoLineResponse]


class PurchaseOrderSummary(BaseModel):
    id: UUID
    po_number: str
    supplier_name: str | None
    currency: str
    line_count: int
    fob_base: Money
    container_numbers: list[str]


# ---------------------------------------------------------------------------- shipments & containers


class ShipmentCreate(BaseModel):
    reference: str = Field(min_length=1, max_length=64)
    carrier_scac: str | None = Field(default=None, min_length=4, max_length=4)
    incoterm: Incoterm | None = None
    origin_unlocode: str | None = Field(default=None, min_length=5, max_length=5)
    destination_unlocode: str | None = Field(default=None, min_length=5, max_length=5)
    etd: date | None = None
    eta: date | None = None


class ShipmentUpdate(ShipmentCreate):
    reference: str | None = Field(default=None, min_length=1, max_length=64)  # type: ignore[assignment]


class ShipmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    reference: str
    carrier_scac: str | None
    incoterm: Incoterm | None
    origin_unlocode: str | None
    destination_unlocode: str | None
    etd: date | None
    eta: date | None


class ContainerCreate(BaseModel):
    container_number: str = Field(min_length=11, max_length=11, pattern=r"^[A-Za-z]{4}[0-9]{7}$")
    shipment_id: UUID | None = None
    carrier_scac: str | None = Field(default=None, min_length=4, max_length=4)
    iso_type: str | None = None

    @field_validator("container_number")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


class ContainerUpdate(BaseModel):
    shipment_id: UUID | None = None
    carrier_scac: str | None = Field(default=None, min_length=4, max_length=4)
    iso_type: str | None = None
    milestone: ContainerMilestone | None = None
    eta: datetime | None = None
    ata: datetime | None = None
    discharged_at: datetime | None = None
    gate_out_at: datetime | None = None
    empty_returned_at: datetime | None = None
    free_days_demurrage: int | None = Field(default=None, ge=0, le=60)
    free_days_detention: int | None = Field(default=None, ge=0, le=60)


class ContainerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    container_number: str
    shipment_id: UUID | None
    carrier_scac: str | None
    iso_type: str | None
    milestone: ContainerMilestone
    tracking_state: TrackingState
    eta: datetime | None
    ata: datetime | None
    discharged_at: datetime | None
    gate_out_at: datetime | None
    empty_returned_at: datetime | None
    free_days_demurrage: int | None
    free_days_detention: int | None
    last_free_day: date | None
    detention_deadline: date | None
    dnd_risk: DndRisk


class ContainerSummary(ContainerResponse):
    shipment_reference: str | None = None
    po_numbers: list[str] = Field(default_factory=list)
    load_count: int = 0
    fob_base: Money = Decimal("0.00")
    allocated_base: Money = Decimal("0.00")
    cost_types_present: list[CostType] = Field(default_factory=list)


class LoadIn(BaseModel):
    po_line_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=4)


class LoadResponse(BaseModel):
    id: UUID
    po_line_id: UUID
    po_id: UUID
    po_number: str
    line_no: int
    sku: str | None
    quantity: Qty
    line_quantity: Qty


# ---------------------------------------------------------------------------- costs


class ManualSplitIn(BaseModel):
    target_type: Literal["container", "po", "po_line"]
    target_id: UUID
    pct: Decimal = Field(gt=0, le=100, max_digits=5, decimal_places=2)


class CostCreate(BaseModel):
    scope: CostScope
    status: CostStatus = CostStatus.ACTUAL
    target_id: UUID
    cost_type: CostType
    amount: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    currency: str
    cost_date: date
    fx_rate: Decimal | None = Field(
        default=None, gt=0, description="Manual override; otherwise ECB rate at cost_date"
    )
    allocation_method: AllocationMethod | None = None
    manual_splits: list[ManualSplitIn] | None = None
    vendor: str | None = Field(default=None, max_length=200)
    invoice_number: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("currency")
    @classmethod
    def _cur(cls, v: str) -> str:
        return currency_code(v)

    @model_validator(mode="after")
    def _manual(self) -> CostCreate:
        if (self.allocation_method == AllocationMethod.MANUAL) != (self.manual_splits is not None):
            raise ValueError("manual_splits is required if and only if allocation_method is MANUAL")
        if self.manual_splits is not None and sum(s.pct for s in self.manual_splits) != Decimal("100.00"):
            raise ValueError("manual_splits must sum to 100.00")
        return self


class CostUpdate(BaseModel):
    cost_type: CostType | None = None
    amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    currency: str | None = None
    cost_date: date | None = None
    fx_rate: Decimal | None = Field(default=None, gt=0)
    allocation_method: AllocationMethod | None = None
    manual_splits: list[ManualSplitIn] | None = None
    vendor: str | None = None
    invoice_number: str | None = None
    notes: str | None = None
    status: CostStatus | None = None
    #: The estimate this cost replaces. Setting it takes that estimate out of the allocation and
    #: makes the pair a variance; only an ACTUAL cost may carry one.
    supersedes_cost_id: UUID | None = None

    @field_validator("currency")
    @classmethod
    def _cur(cls, v: str | None) -> str | None:
        return None if v is None else currency_code(v)


class CostResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    scope: CostScope
    shipment_id: UUID | None
    container_id: UUID | None
    po_id: UUID | None
    po_line_id: UUID | None
    cost_type: CostType
    amount: Money
    currency: str
    fx_rate: Rate
    fx_date: date
    fx_source: str
    amount_base: Money
    allocation_method: AllocationMethod
    manual_splits: list[dict[str, Any]] | None
    cost_date: date
    vendor: str | None
    invoice_number: str | None
    notes: str | None
    status: CostStatus
    supersedes_cost_id: UUID | None
    closed_at: datetime | None
    close_reason: str | None
    created_at: datetime


class CostClose(BaseModel):
    """Closing an estimate no invoice will ever match."""

    reason: str = Field(min_length=1, max_length=500)


# ---------------------------------------------------------------------------- landed costs


class ReportWarning(BaseModel):
    cost_id: UUID
    code: str
    message: str
    amount_base: Money
    load_ids: list[UUID]
    # "PO-2026-101 #1 SKU" per affected load, so the UI can compose a translated sentence
    # instead of parsing `message`.
    load_labels: list[str] = []


class CostTypeSplit(BaseModel):
    estimated: Money = Decimal("0.00")
    actual: Money = Decimal("0.00")


class ReportLine(BaseModel):
    load_id: UUID
    container_id: UUID
    container_number: str
    po_id: UUID
    po_number: str
    line_no: int
    sku: str | None
    description: str | None
    quantity: Qty
    fob: Money
    allocated: Money
    vat: Money
    landed: Money
    unit_landed_cost: Qty
    estimated: Money
    actual: Money
    variance: Money
    by_cost_type: dict[str, Money]


class LandedCostReport(BaseModel):
    base_currency: str
    #: fob, allocated, vat, landed, unallocated, estimated, actual, variance
    totals: dict[str, Money]
    #: Share of the cost types on this scope that have a real invoice, 0 to 1. Null when none is
    #: expected yet.
    completeness: Decimal | None = None
    by_cost_type: dict[str, Money]
    by_cost_type_detail: dict[str, CostTypeSplit] = Field(default_factory=dict)
    lines: list[ReportLine]
    costs: list[CostResponse]
    warnings: list[ReportWarning]


class PreviewRequest(BaseModel):
    container_id: UUID | None = None
    shipment_id: UUID | None = None
    po_id: UUID | None = None
    method_overrides: dict[CostType, AllocationMethod] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _one(self) -> PreviewRequest:
        if sum(x is not None for x in (self.container_id, self.shipment_id, self.po_id)) != 1:
            raise ValueError("exactly one of container_id, shipment_id, po_id is required")
        return self


class IntegrityReport(BaseModel):
    ok: bool
    costs_checked: int
    mismatches: list[dict[str, str]]


# ---------------------------------------------------------------------------- imports


class ImportJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    kind: ImportKind
    status: ImportStatus
    original_filename: str | None
    encoding: str | None
    delimiter: str | None
    columns: list[str]
    mapping: dict[str, str]
    row_count: int
    error_count: int
    report: dict[str, Any]
    created_at: datetime
    committed_at: datetime | None


class ImportValidateRequest(BaseModel):
    mapping: dict[str, str]


class ImportCommitRequest(BaseModel):
    mapping: dict[str, str] | None = None
    on_error: Literal["skip_rows", "abort"] = "skip_rows"


# ---------------------------------------------------------------------------- fx


class FxRateResponse(BaseModel):
    base: str
    quote: str
    rate_date: date
    rate: Rate
    source: str


# ---------------------------------------------------------------------------- tracking


class TrackingEventCreate(BaseModel):
    """A milestone typed in by hand. `occurred_at` is when it happened, not when it was entered."""

    code: MilestoneCode
    occurred_at: datetime
    is_estimate: bool = False
    location_unlocode: str | None = Field(default=None, min_length=5, max_length=5)
    location_name: str | None = None
    vessel_name: str | None = None
    voyage: str | None = None
    note: str | None = None


class TrackingEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    container_id: UUID
    provider: str
    code: MilestoneCode
    occurred_at: datetime
    is_estimate: bool
    location_unlocode: str | None
    location_name: str | None
    vessel_name: str | None
    voyage: str | None
    raw_description: str | None
    source: str
    inserted_at: datetime


class TrackingSubscriptionCreate(BaseModel):
    """`provider_ref` is the provider's own handle for this box. Leave it out when the provider is
    subscribed through its API; give it when deliveries arrive webhook-only (no API key)."""

    provider: str = "manual"
    provider_ref: str | None = None
    identifier_type: Literal["container", "bill_of_lading", "booking"] = "container"
    identifier: str | None = None  # defaults to the container number


class TrackingSubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    container_id: UUID
    provider: str
    provider_ref: str | None
    status: str
    last_error: str | None
    subscribed_at: datetime | None
    ended_at: datetime | None


class EtaHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    container_id: UUID
    eta: datetime
    previous_eta: datetime | None
    delta_hours: Decimal
    severity: str
    source: str
    recorded_at: datetime


class WebhookAck(BaseModel):
    """What a provider gets back. Always 200 once the delivery is stored; `status` says what we did
    with it, and a provider must not retry on `duplicate` or `failed`."""

    delivery_id: UUID
    status: Literal["processed", "duplicate", "failed", "unroutable"]
    events_ingested: int = 0
    detail: str | None = None


# ---------------------------------------------------------------------------- alerts


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    container_id: UUID | None
    kind: AlertKind
    severity: AlertSeverity
    title: str
    body: str
    payload: dict[str, Any]
    created_at: datetime
    read_at: datetime | None


class AlertsRead(BaseModel):
    marked: int


# ---------------------------------------------------------------------------- invoices


class InvoiceLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    line_no: int
    description: str
    amount: Money
    currency: str
    cost_type: CostType | None
    scope: CostScope | None
    target_id: UUID | None
    confidence: Decimal
    accepted: bool
    notes: str | None
    cost_id: UUID | None


class InvoiceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    status: InvoiceStatus
    vendor: str | None
    invoice_number: str | None
    invoice_date: date | None
    currency: str | None
    total_amount: Money | None
    vat_amount: Money | None
    confidence: Decimal | None
    extractor: str | None
    error: str | None
    document_id: UUID
    filename: str | None = None
    created_at: datetime


class InvoiceResponse(InvoiceSummary):
    lines: list[InvoiceLineResponse] = Field(default_factory=list)
    document_url: str  # this API's own route; the bytes never come from a storage URL
    notes: list[str] = Field(default_factory=list)


class InvoiceLineUpdate(BaseModel):
    """A correction made by a person. Everything is optional; nothing is inferred."""

    amount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    currency: str | None = None
    cost_type: CostType | None = None
    scope: CostScope | None = None
    target_id: UUID | None = None
    accepted: bool | None = None
    description: str | None = None

    @field_validator("currency")
    @classmethod
    def _currency(cls, v: str | None) -> str | None:
        return None if v is None else currency_code(v)


class InvoiceConfirmResponse(BaseModel):
    invoice: InvoiceResponse
    costs_created: int
    cost_ids: list[UUID]
    #: Estimates these costs replaced, when exactly one was waiting for them.
    superseded_estimate_ids: list[UUID] = Field(default_factory=list)
    #: What the confirmation deliberately did not decide, in plain words.
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------- audit log


class AuditEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    actor_user_id: UUID | None
    action: str
    entity_type: str
    entity_id: UUID | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    at: datetime


class AuditPage(BaseModel):
    """A page of history, newest first. `next_cursor` is null when there is nothing older."""

    entries: list[AuditEntryResponse]
    next_cursor: str | None = None


# ---------------------------------------------------------------------------- rate cards


class RateCardIn(BaseModel):
    cost_type: CostType
    scope: Literal[CostScope.CONTAINER, CostScope.SHIPMENT] = CostScope.CONTAINER
    basis: RateBasis = RateBasis.FLAT
    amount: Decimal = Field(ge=0, max_digits=14, decimal_places=4)
    currency: str
    hs_code: str | None = Field(default=None, max_length=12)
    notes: str | None = None

    @field_validator("currency")
    @classmethod
    def _cur(cls, v: str) -> str:
        return currency_code(v)


class RateCardUpdate(BaseModel):
    basis: RateBasis | None = None
    amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=4)
    currency: str | None = None
    hs_code: str | None = None
    notes: str | None = None

    @field_validator("currency")
    @classmethod
    def _cur(cls, v: str | None) -> str | None:
        return None if v is None else currency_code(v)


class RateCardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    cost_type: CostType
    scope: CostScope
    basis: RateBasis
    amount: Qty
    currency: str
    hs_code: str | None
    notes: str | None


class EstimateResponse(BaseModel):
    """What applying the rate cards to a container produced, and what it did not."""

    created: list[CostResponse]
    skipped: dict[str, str]  # cost type -> the reason, in plain words


# ---------------------------------------------------------------------------- variance report


class VarianceRow(BaseModel):
    key: str  # a cost type, or a purchase order number
    label: str
    estimated: Money
    actual: Money
    variance: Money


class VarianceReport(BaseModel):
    """What the month's invoices cost against what was expected of them.

    Only costs that replaced an estimate appear: an invoice nobody forecast has nothing to differ
    from, and counting it as a 100 % overrun would be a lie by arithmetic.
    """

    period: str  # YYYY-MM
    base_currency: str
    estimated: Money
    actual: Money
    variance: Money
    pairs: int
    by_cost_type: list[VarianceRow]
    by_purchase_order: list[VarianceRow]
