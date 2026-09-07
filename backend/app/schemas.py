"""API schemas. Money is Decimal in, string out ("1234.56"). Never float."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator

from app.costing import AllocationMethod
from app.models import ContainerStatus, CostType

Money = Annotated[Decimal, PlainSerializer(lambda d: f"{d:.2f}", return_type=str, when_used="json")]
Pct = Annotated[Decimal, PlainSerializer(lambda d: f"{d:.2f}", return_type=str, when_used="json")]
Unit = Annotated[Decimal, PlainSerializer(lambda d: f"{d:.4f}", return_type=str, when_used="json")]


def _upper3(v: str) -> str:
    v = v.strip().upper()
    if len(v) != 3 or not v.isalpha():
        raise ValueError("currency must be a 3-letter ISO code")
    return v


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    base_currency: str


class ContainerCreate(BaseModel):
    container_number: str = Field(min_length=11, max_length=11, pattern=r"^[A-Za-z]{4}[0-9]{7}$")
    carrier: str | None = None

    @field_validator("container_number")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


class ContainerUpdate(BaseModel):
    status: ContainerStatus | None = None
    carrier: str | None = None


class ContainerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    container_number: str
    carrier: str | None
    status: ContainerStatus


class CostCreate(BaseModel):
    cost_type: CostType
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    currency: str

    @field_validator("currency")
    @classmethod
    def _cur(cls, v: str) -> str:
        return _upper3(v)


class CostResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    cost_type: CostType
    amount: Money
    currency: str


class ImportRowError(BaseModel):
    row: int
    code: str
    message: str


class ImportResponse(BaseModel):
    status: str
    rows_processed: int
    rows_skipped: list[ImportRowError]
    purchase_orders_created: int
    containers_created: int
    containers_linked: int
    detected_columns: list[str]


class LandedCostWarning(BaseModel):
    code: str
    message: str


class LandedCostBreakdown(BaseModel):
    po_id: UUID
    po_number: str
    supplier_name: str | None
    fob_value: Money
    allocation_pct: Pct
    allocated_costs: Money
    true_landed_cost: Money


class LandedCostResponse(BaseModel):
    container: ContainerResponse
    base_currency: str
    allocation_method: AllocationMethod | None
    total_additional_costs: Money
    total_allocated: Money
    unallocated: Money
    breakdown: list[LandedCostBreakdown]
    raw_costs: list[CostResponse]
    warnings: list[LandedCostWarning]


class Problem(BaseModel):
    """RFC 9457-ish error body."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    errors: list[dict[str, str]] | None = None
