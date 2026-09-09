"""Phase 1 schema.

Rules: UUID keys, `org_id` on every business table (denormalised, required for RLS), NUMERIC for money and
quantities, timestamps in UTC. A cost has exactly one scope and is always allocated down to the leaves,
`container_loads` (purchase-order line x container x quantity).
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, ClassVar

from sqlalchemy import (
    CHAR,
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: ClassVar[dict[Any, Any]] = {dict[str, Any]: JSONB().with_variant(JSON(), "sqlite")}


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------- enums


class AllocationMethod(enum.StrEnum):
    BY_VALUE = "BY_VALUE"
    BY_WEIGHT = "BY_WEIGHT"
    BY_VOLUME = "BY_VOLUME"
    BY_QUANTITY = "BY_QUANTITY"
    MANUAL = "MANUAL"
    BY_CIF_VALUE = "BY_CIF_VALUE"
    BY_THEORETICAL_DUTY = "BY_THEORETICAL_DUTY"


class CostScope(enum.StrEnum):
    SHIPMENT = "SHIPMENT"
    CONTAINER = "CONTAINER"
    PO = "PO"
    PO_LINE = "PO_LINE"


class CostType(enum.StrEnum):
    OCEAN_FREIGHT = "OCEAN_FREIGHT"
    AIR_FREIGHT = "AIR_FREIGHT"
    INSURANCE = "INSURANCE"
    ORIGIN_CHARGES = "ORIGIN_CHARGES"
    THC = "THC"
    BL_FEE = "BL_FEE"
    CUSTOMS_DUTY = "CUSTOMS_DUTY"
    CUSTOMS_BROKERAGE = "CUSTOMS_BROKERAGE"
    IMPORT_VAT = "IMPORT_VAT"
    DRAYAGE = "DRAYAGE"
    DEMURRAGE = "DEMURRAGE"
    DETENTION = "DETENTION"
    WAREHOUSING = "WAREHOUSING"
    INSPECTION = "INSPECTION"
    BANK_FEES = "BANK_FEES"
    OTHER = "OTHER"


class ContainerMilestone(enum.StrEnum):
    BOOKED = "BOOKED"
    GATE_IN_FULL_ORIGIN = "GATE_IN_FULL_ORIGIN"
    LOADED = "LOADED"
    VESSEL_DEPARTED = "VESSEL_DEPARTED"
    VESSEL_ARRIVED = "VESSEL_ARRIVED"
    DISCHARGED = "DISCHARGED"
    AVAILABLE_FOR_PICKUP = "AVAILABLE_FOR_PICKUP"
    GATE_OUT_FULL = "GATE_OUT_FULL"
    DELIVERED = "DELIVERED"
    GATE_IN_EMPTY_RETURN = "GATE_IN_EMPTY_RETURN"


class MilestoneCode(enum.StrEnum):
    """Tracking timeline vocabulary: every milestone a provider can report.

    A superset of `ContainerMilestone` (the coarser state carried on the container itself); the extra
    codes — empty pickup at origin, transshipment and rail legs, `UNKNOWN` — stay in the timeline.
    """

    BOOKED = "BOOKED"
    GATE_OUT_EMPTY_ORIGIN = "GATE_OUT_EMPTY_ORIGIN"
    GATE_IN_FULL_ORIGIN = "GATE_IN_FULL_ORIGIN"
    LOADED = "LOADED"
    VESSEL_DEPARTED = "VESSEL_DEPARTED"
    TRANSSHIPMENT_ARRIVED = "TRANSSHIPMENT_ARRIVED"
    TRANSSHIPMENT_DISCHARGED = "TRANSSHIPMENT_DISCHARGED"
    TRANSSHIPMENT_LOADED = "TRANSSHIPMENT_LOADED"
    TRANSSHIPMENT_DEPARTED = "TRANSSHIPMENT_DEPARTED"
    VESSEL_ARRIVED = "VESSEL_ARRIVED"
    DISCHARGED = "DISCHARGED"
    AVAILABLE_FOR_PICKUP = "AVAILABLE_FOR_PICKUP"
    GATE_OUT_FULL = "GATE_OUT_FULL"
    RAIL_LOADED = "RAIL_LOADED"
    RAIL_DEPARTED = "RAIL_DEPARTED"
    RAIL_ARRIVED = "RAIL_ARRIVED"
    RAIL_UNLOADED = "RAIL_UNLOADED"
    DELIVERED = "DELIVERED"
    GATE_IN_EMPTY_RETURN = "GATE_IN_EMPTY_RETURN"
    UNKNOWN = "UNKNOWN"


class TrackingState(enum.StrEnum):
    UNTRACKED = "UNTRACKED"
    MANUAL = "MANUAL"
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    FAILED = "FAILED"
    ENDED = "ENDED"


class DndRisk(enum.StrEnum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    INCURRING = "INCURRING"


class MemberRole(enum.StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"
    VIEWER = "VIEWER"


class Incoterm(enum.StrEnum):
    EXW = "EXW"
    FCA = "FCA"
    FOB = "FOB"
    CFR = "CFR"
    CIF = "CIF"
    DAP = "DAP"
    DDP = "DDP"


class ImportKind(enum.StrEnum):
    PURCHASE_ORDERS = "PURCHASE_ORDERS"  # one row per PO line
    LEGACY_PO_CONTAINER = "LEGACY_PO_CONTAINER"  # Phase 0 format: one row per PO with a container


class ImportStatus(enum.StrEnum):
    PARSED = "PARSED"
    VALIDATED = "VALIDATED"
    DONE = "DONE"
    FAILED = "FAILED"


# ---------------------------------------------------------------------------- mixins


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )


class OrgScoped:
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)


# ---------------------------------------------------------------------------- identity


class Organization(Timestamped, Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str | None] = mapped_column(String, unique=True)
    external_id: Mapped[str | None] = mapped_column(String, unique=True)  # Clerk organization id
    base_currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, default="EUR")
    default_allocation_method: Mapped[AllocationMethod] = mapped_column(
        Enum(AllocationMethod, name="allocation_method"), nullable=False, default=AllocationMethod.BY_VALUE
    )
    default_incoterm: Mapped[Incoterm | None] = mapped_column(Enum(Incoterm, name="incoterm"))
    free_days_demurrage: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    free_days_detention: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    settings: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)


class User(Timestamped, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    external_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)  # Clerk user id
    email: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str | None] = mapped_column(String)


class Membership(Base):
    __tablename__ = "memberships"

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role: Mapped[MemberRole] = mapped_column(
        Enum(MemberRole, name="member_role"), nullable=False, default=MemberRole.MEMBER
    )


# ---------------------------------------------------------------------------- business


class Supplier(Timestamped, OrgScoped, Base):
    __tablename__ = "suppliers"
    __table_args__ = (UniqueConstraint("org_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    country: Mapped[str | None] = mapped_column(CHAR(2))
    default_currency: Mapped[str | None] = mapped_column(CHAR(3))


class Shipment(Timestamped, OrgScoped, Base):
    __tablename__ = "shipments"
    __table_args__ = (UniqueConstraint("org_id", "reference"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    reference: Mapped[str] = mapped_column(String, nullable=False)  # BL or booking
    carrier_scac: Mapped[str | None] = mapped_column(CHAR(4))
    incoterm: Mapped[Incoterm | None] = mapped_column(Enum(Incoterm, name="incoterm"))
    origin_unlocode: Mapped[str | None] = mapped_column(CHAR(5))
    destination_unlocode: Mapped[str | None] = mapped_column(CHAR(5))
    etd: Mapped[date | None] = mapped_column(Date)
    eta: Mapped[date | None] = mapped_column(Date)

    containers: Mapped[list[Container]] = relationship(back_populates="shipment")


class Container(Timestamped, OrgScoped, Base):
    __tablename__ = "containers"
    __table_args__ = (
        CheckConstraint("container_number ~ '^[A-Z]{4}[0-9]{7}$'", name="iso6346"),
        Index(
            "uq_containers_active_number",
            "org_id",
            "container_number",
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    shipment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("shipments.id"), index=True)
    container_number: Mapped[str] = mapped_column(CHAR(11), nullable=False)
    iso_type: Mapped[str | None] = mapped_column(String)
    carrier_scac: Mapped[str | None] = mapped_column(CHAR(4))
    milestone: Mapped[ContainerMilestone] = mapped_column(
        Enum(ContainerMilestone, name="container_milestone"),
        nullable=False,
        default=ContainerMilestone.BOOKED,
    )
    tracking_state: Mapped[TrackingState] = mapped_column(
        Enum(TrackingState, name="tracking_state"), nullable=False, default=TrackingState.MANUAL
    )
    eta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ata: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discharged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    gate_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    empty_returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    free_days_demurrage: Mapped[int | None] = mapped_column(Integer)
    free_days_detention: Mapped[int | None] = mapped_column(Integer)
    last_free_day: Mapped[date | None] = mapped_column(Date)
    dnd_risk: Mapped[DndRisk] = mapped_column(
        Enum(DndRisk, name="dnd_risk"), nullable=False, default=DndRisk.NONE
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    shipment: Mapped[Shipment | None] = relationship(back_populates="containers")
    loads: Mapped[list[ContainerLoad]] = relationship(
        back_populates="container", cascade="all, delete-orphan"
    )


class PurchaseOrder(Timestamped, OrgScoped, Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (UniqueConstraint("org_id", "po_number"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    po_number: Mapped[str] = mapped_column(String, nullable=False)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("suppliers.id"), index=True)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False, default=Decimal("1"))
    fx_date: Mapped[date | None] = mapped_column(Date)
    incoterm: Mapped[Incoterm | None] = mapped_column(Enum(Incoterm, name="incoterm"))
    order_date: Mapped[date | None] = mapped_column(Date)

    supplier: Mapped[Supplier | None] = relationship()
    lines: Mapped[list[PurchaseOrderLine]] = relationship(
        back_populates="purchase_order", cascade="all, delete-orphan", order_by="PurchaseOrderLine.line_no"
    )


class PurchaseOrderLine(OrgScoped, Base):
    __tablename__ = "po_lines"
    __table_args__ = (
        UniqueConstraint("po_id", "line_no"),
        CheckConstraint("quantity > 0", name="qty_positive"),
        CheckConstraint("unit_price >= 0", name="price_nonneg"),
        Index("ix_po_lines_org_sku", "org_id", "sku"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    po_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("purchase_orders.id"), nullable=False, index=True)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    sku: Mapped[str | None] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(String)
    hs_code: Mapped[str | None] = mapped_column(String)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)  # in PO currency
    unit_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    unit_volume_cbm: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    duty_rate: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))  # 0.0450 = 4.5 %

    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="lines")
    loads: Mapped[list[ContainerLoad]] = relationship(back_populates="po_line", cascade="all, delete-orphan")


class ContainerLoad(OrgScoped, Base):
    """The leaf: a quantity of one PO line inside one container."""

    __tablename__ = "container_loads"
    __table_args__ = (
        UniqueConstraint("container_id", "po_line_id"),
        CheckConstraint("quantity > 0", name="qty_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    container_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("containers.id"), nullable=False, index=True)
    po_line_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("po_lines.id"), nullable=False, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)

    container: Mapped[Container] = relationship(back_populates="loads")
    po_line: Mapped[PurchaseOrderLine] = relationship(back_populates="loads")


class Cost(Timestamped, OrgScoped, Base):
    __tablename__ = "costs"
    __table_args__ = (
        CheckConstraint("num_nonnulls(shipment_id, container_id, po_id, po_line_id) = 1", name="one_scope"),
        CheckConstraint("(allocation_method = 'MANUAL') = (manual_splits IS NOT NULL)", name="manual_splits"),
        CheckConstraint("amount >= 0", name="amount_nonneg"),
        Index(
            "uq_costs_invoice_line",
            "org_id",
            "vendor",
            "invoice_number",
            "cost_type",
            unique=True,
            postgresql_where=text("invoice_number IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    scope: Mapped[CostScope] = mapped_column(Enum(CostScope, name="cost_scope"), nullable=False)
    shipment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("shipments.id"), index=True)
    container_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("containers.id"), index=True)
    po_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    po_line_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("po_lines.id"), index=True)
    cost_type: Mapped[CostType] = mapped_column(Enum(CostType, name="cost_type"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    fx_date: Mapped[date] = mapped_column(Date, nullable=False)
    fx_source: Mapped[str] = mapped_column(String, nullable=False)  # ecb | manual | same
    amount_base: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    allocation_method: Mapped[AllocationMethod] = mapped_column(
        Enum(AllocationMethod, name="allocation_method"), nullable=False
    )
    manual_splits: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB(none_as_null=True))
    cost_date: Mapped[date] = mapped_column(Date, nullable=False)
    vendor: Mapped[str | None] = mapped_column(String)
    invoice_number: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(String)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    allocations: Mapped[list[CostAllocation]] = relationship(
        back_populates="cost", cascade="all, delete-orphan"
    )


class CostAllocation(OrgScoped, Base):
    """Materialised output of the engine. Recomputed in the same transaction as any write that affects it."""

    __tablename__ = "cost_allocations"
    __table_args__ = (UniqueConstraint("cost_id", "container_load_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    cost_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("costs.id", ondelete="CASCADE"), nullable=False)
    container_load_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("container_loads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount_base: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    cost: Mapped[Cost] = relationship(back_populates="allocations")


class FxRate(Base):
    __tablename__ = "fx_rates"

    base: Mapped[str] = mapped_column(CHAR(3), primary_key=True)
    quote: Mapped[str] = mapped_column(CHAR(3), primary_key=True)
    rate_date: Mapped[date] = mapped_column(Date, primary_key=True)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)  # 1 quote = rate base
    source: Mapped[str] = mapped_column(String, nullable=False)


# ---------------------------------------------------------------------------- imports


class ImportJob(Timestamped, OrgScoped, Base):
    __tablename__ = "import_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    kind: Mapped[ImportKind] = mapped_column(Enum(ImportKind, name="import_kind"), nullable=False)
    status: Mapped[ImportStatus] = mapped_column(
        Enum(ImportStatus, name="import_status"), nullable=False, default=ImportStatus.PARSED
    )
    original_filename: Mapped[str | None] = mapped_column(String)
    sha256: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[bytes] = mapped_column(nullable=False)
    encoding: Mapped[str | None] = mapped_column(String)
    delimiter: Mapped[str | None] = mapped_column(String)
    columns: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    mapping: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    report: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportMapping(OrgScoped, Base):
    __tablename__ = "import_mappings"
    __table_args__ = (UniqueConstraint("org_id", "kind", "header_signature"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    kind: Mapped[ImportKind] = mapped_column(Enum(ImportKind, name="import_kind"), nullable=False)
    header_signature: Mapped[str] = mapped_column(String, nullable=False)
    mapping: Mapped[dict[str, Any]] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )


# ---------------------------------------------------------------------------- tracking


class TrackingSubscription(Timestamped, OrgScoped, Base):
    """One container watched at one provider. `provider_ref` is the provider's own handle for it;
    it is null while a webhook-only deployment routes deliveries by container number."""

    __tablename__ = "tracking_subscriptions"
    __table_args__ = (
        UniqueConstraint("container_id"),
        UniqueConstraint("provider", "provider_ref"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    container_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("containers.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    provider_ref: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")  # pending|active|failed
    last_error: Mapped[str | None] = mapped_column(String)
    subscribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WebhookDelivery(Base):
    """Raw provider deliveries, kept whole. Not org-scoped and not under RLS: a delivery is written
    before we know which tenant it belongs to, and it holds no tenant data of its own beyond the
    provider's payload. `(provider, delivery_id)` is the idempotency key."""

    __tablename__ = "webhook_deliveries"
    __table_args__ = (UniqueConstraint("provider", "delivery_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    delivery_id: Mapped[str] = mapped_column(String, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    headers: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)
    body: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    signature_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="received"
    )  # received|processed|failed
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(String)


class TrackingEvent(OrgScoped, Base):
    """Append-only milestone history. Nothing here is ever updated: a snapshot replayed inserts
    nothing (ON CONFLICT DO NOTHING), and an estimate that becomes actual is a new row, because the
    carrier's earlier promise is evidence in a demurrage dispute."""

    __tablename__ = "tracking_events"
    __table_args__ = (
        UniqueConstraint("org_id", "container_id", "provider", "provider_event_key"),
        Index("ix_tracking_events_container_time", "container_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    container_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("containers.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    provider_event_key: Mapped[str] = mapped_column(String, nullable=False)
    code: Mapped[MilestoneCode] = mapped_column(Enum(MilestoneCode, name="milestone_code"), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_estimate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    location_unlocode: Mapped[str | None] = mapped_column(CHAR(5))
    location_name: Mapped[str | None] = mapped_column(String)
    vessel_name: Mapped[str | None] = mapped_column(String)
    voyage: Mapped[str | None] = mapped_column(String)
    raw_description: Mapped[str | None] = mapped_column(String)
    source: Mapped[str] = mapped_column(String, nullable=False, default="unknown")
    delivery_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("webhook_deliveries.id"))
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)


class EtaHistory(OrgScoped, Base):
    """Every ETA move worth telling the user about (more than 12 h). `severity` is `warning` past 48 h."""

    __tablename__ = "eta_history"
    __table_args__ = (Index("ix_eta_history_container", "container_id", "recorded_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    container_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("containers.id"), nullable=False)
    eta: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    previous_eta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delta_hours: Mapped[Decimal] = mapped_column(Numeric(8, 1), nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False, default="info")  # info|warning
    source: Mapped[str] = mapped_column(String, nullable=False, default="unknown")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)


# Tables that carry org_id and get a Row Level Security policy in migration 0003 (0004 for tracking).
RLS_TABLES = [
    "suppliers",
    "shipments",
    "containers",
    "purchase_orders",
    "po_lines",
    "container_loads",
    "costs",
    "cost_allocations",
    "import_jobs",
    "import_mappings",
    "tracking_subscriptions",
    "tracking_events",
    "eta_history",
]
