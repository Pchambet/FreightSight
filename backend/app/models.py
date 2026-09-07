"""Phase 0 schema: the original tables, minus the fake tracking metadata, plus a base currency per org.

The many-to-many `allocation_percentage` is kept for compatibility but is no longer the source of truth
for allocation (see app.costing). Phase 1 replaces it with container_loads.
"""

import enum
import uuid
from decimal import Decimal

from sqlalchemy import CHAR, Enum, ForeignKey, MetaData, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
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


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    base_currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, default="EUR")

    purchase_orders: Mapped[list["PurchaseOrder"]] = relationship(back_populates="organization")
    containers: Mapped[list["Container"]] = relationship(back_populates="organization")


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (UniqueConstraint("org_id", "po_number"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    po_number: Mapped[str] = mapped_column(String, nullable=False)
    supplier_name: Mapped[str | None] = mapped_column(String)
    total_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0"))

    organization: Mapped[Organization] = relationship(back_populates="purchase_orders")
    container_links: Mapped[list["ContainerPurchaseOrder"]] = relationship(back_populates="purchase_order")


class ContainerStatus(enum.StrEnum):
    PENDING = "PENDING"
    IN_TRANSIT = "IN_TRANSIT"
    DISCHARGED = "DISCHARGED"
    DELIVERED = "DELIVERED"


class Container(Base):
    __tablename__ = "containers"
    __table_args__ = (UniqueConstraint("org_id", "container_number"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    container_number: Mapped[str] = mapped_column(String, nullable=False)
    carrier: Mapped[str | None] = mapped_column(String)
    status: Mapped[ContainerStatus] = mapped_column(
        Enum(ContainerStatus, name="containerstatus"), nullable=False, default=ContainerStatus.PENDING
    )

    organization: Mapped[Organization] = relationship(back_populates="containers")
    po_links: Mapped[list["ContainerPurchaseOrder"]] = relationship(
        back_populates="container", cascade="all, delete-orphan"
    )
    costs: Mapped[list["Cost"]] = relationship(back_populates="container", cascade="all, delete-orphan")


class ContainerPurchaseOrder(Base):
    __tablename__ = "container_purchase_order"

    container_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("containers.id"), primary_key=True)
    po_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("purchase_orders.id"), primary_key=True, index=True)
    # Deprecated. Only honoured when every link on the container has a value and they sum to 100.00.
    allocation_percentage: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    container: Mapped[Container] = relationship(back_populates="po_links")
    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="container_links")


class CostType(enum.StrEnum):
    OCEAN_FREIGHT = "OCEAN_FREIGHT"
    CUSTOMS = "CUSTOMS"
    DRAYAGE = "DRAYAGE"
    DEMURRAGE = "DEMURRAGE"


class Cost(Base):
    __tablename__ = "costs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    container_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("containers.id"), nullable=False, index=True)
    cost_type: Mapped[CostType] = mapped_column(Enum(CostType, name="costtype"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)

    container: Mapped[Container] = relationship(back_populates="costs")
