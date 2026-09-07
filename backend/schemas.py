from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime

class ContainerCreate(BaseModel):
    container_number: str = Field(..., description="Unique container identifier")
    carrier: Optional[str] = None
    org_id: UUID

class ContainerResponse(BaseModel):
    id: UUID
    container_number: str
    carrier: Optional[str] = None
    status: str
    vizion_reference_id: Optional[str] = None

    class Config:
        from_attributes = True

class CostCreate(BaseModel):
    cost_type: str = Field(..., description="Type of the cost (e.g., OCEAN_FREIGHT)")
    amount: float = Field(..., gt=0, description="Amount of the cost")
    currency: str = Field(default="USD", max_length=3)

class WebhookPayload(BaseModel):
    # Depending on Vizion's actual payload, using a generic dict or more specific schema
    event: Optional[str] = None
    container_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None

class LandedCostBreakdown(BaseModel):
    po_number: str
    supplier_name: Optional[str] = None
    fob_value: float
    allocation_pct: float
    allocated_freight_and_duty: float
    true_landed_cost: float

class LandedCostResponse(BaseModel):
    container_number: str
    total_additional_costs: float
    breakdown: List[LandedCostBreakdown]
    raw_costs: List[Dict[str, Any]]
