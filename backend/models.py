from sqlalchemy import Column, String, Numeric, Enum, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship
import uuid
import enum

Base = declarative_base()

class Organization(Base):
    __tablename__ = 'organizations'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    
    purchase_orders = relationship("PurchaseOrder", back_populates="organization")
    containers = relationship("Container", back_populates="organization")

class PurchaseOrder(Base):
    __tablename__ = 'purchase_orders'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id'), nullable=False)
    po_number = Column(String, nullable=False)
    supplier_name = Column(String)
    total_value = Column(Numeric(12, 2))
    
    organization = relationship("Organization", back_populates="purchase_orders")
    container_links = relationship("ContainerPurchaseOrder", back_populates="purchase_order")

class ContainerStatus(enum.Enum):
    PENDING = "PENDING"
    IN_TRANSIT = "IN_TRANSIT"
    DISCHARGED = "DISCHARGED"
    DELIVERED = "DELIVERED"

class Container(Base):
    __tablename__ = 'containers'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id'), nullable=False)
    container_number = Column(String, nullable=False)
    carrier = Column(String)
    status = Column(Enum(ContainerStatus), default=ContainerStatus.PENDING)
    
    organization = relationship("Organization", back_populates="containers")
    po_links = relationship("ContainerPurchaseOrder", back_populates="container")
    costs = relationship("Cost", back_populates="container")
    vizion_metadata = relationship("VizionTrackingMetadata", back_populates="container", uselist=False)

class ContainerPurchaseOrder(Base):
    __tablename__ = 'container_purchase_order'
    container_id = Column(UUID(as_uuid=True), ForeignKey('containers.id'), primary_key=True)
    po_id = Column(UUID(as_uuid=True), ForeignKey('purchase_orders.id'), primary_key=True)
    allocation_percentage = Column(Numeric(5, 2)) # e.g. 50.00 for 50%
    
    container = relationship("Container", back_populates="po_links")
    purchase_order = relationship("PurchaseOrder", back_populates="container_links")

class CostType(enum.Enum):
    OCEAN_FREIGHT = "OCEAN_FREIGHT"
    CUSTOMS = "CUSTOMS"
    DRAYAGE = "DRAYAGE"
    DEMURRAGE = "DEMURRAGE"

class Cost(Base):
    __tablename__ = 'costs'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    container_id = Column(UUID(as_uuid=True), ForeignKey('containers.id'), nullable=False)
    cost_type = Column(Enum(CostType), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String, default="USD")
    
    container = relationship("Container", back_populates="costs")

class VizionTrackingMetadata(Base):
    __tablename__ = 'vizion_tracking_metadata'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    container_id = Column(UUID(as_uuid=True), ForeignKey('containers.id'), unique=True, nullable=False)
    vizion_reference_id = Column(String)
    last_event_code = Column(String)
    estimated_arrival_date = Column(DateTime)
    
    container = relationship("Container", back_populates="vizion_metadata")
