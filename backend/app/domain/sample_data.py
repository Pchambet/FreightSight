"""Demo dataset: the T5 reference case of the plan, with names an importer would recognise.

Everything is priced in the organization's base currency, so the seed never needs an FX lookup and the
figures match the reference case exactly: allocated 3500.00 over two containers, PO-A unit landed cost
11.6458, PO-B 23.7083. Seeded in the caller's transaction, allocations included.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.costing.service import recompute_org
from app.domain.models import (
    AllocationMethod,
    Container,
    ContainerLoad,
    ContainerMilestone,
    Cost,
    CostScope,
    CostType,
    Incoterm,
    Organization,
    PurchaseOrder,
    PurchaseOrderLine,
    Shipment,
    Supplier,
    TrackingState,
)

FREE_DAYS_DEMURRAGE = 7


@dataclass(frozen=True)
class SampleData:
    """What the seed created, for the API response and for the caller to finish (D&D derivation)."""

    containers: list[Container]
    supplier_count: int
    purchase_order_count: int
    cost_count: int
    shipment_reference: str


def has_data(db: Session, org_id: UUID) -> bool:
    """True as soon as the organization holds a purchase order or a container."""
    po = db.scalar(select(PurchaseOrder.id).where(PurchaseOrder.org_id == org_id).limit(1))
    container = db.scalar(select(Container.id).where(Container.org_id == org_id).limit(1))
    return po is not None or container is not None


def seed_sample_data(db: Session, org: Organization) -> SampleData:
    """Create the demo dataset for `org` and materialise its allocations. Caller commits."""
    now = datetime.now(UTC)
    today = now.date()
    currency = org.base_currency

    tyres = Supplier(org_id=org.id, name="Zhejiang Kaiyuan Tyre Co.", country="CN", default_currency=currency)
    mats = Supplier(org_id=org.id, name="Ningbo Hanwei Housewares", country="CN", default_currency=currency)
    db.add_all([tyres, mats])
    db.flush()

    po_a = PurchaseOrder(
        org_id=org.id,
        po_number="PO-2026-014",
        supplier_id=tyres.id,
        currency=currency,
        fx_rate=Decimal("1"),
        incoterm=Incoterm.FOB,
        order_date=today - timedelta(days=75),
    )
    line_a = PurchaseOrderLine(
        org_id=org.id,
        line_no=1,
        sku="TYR-20555R16-91V",
        description="Passenger tyre 205/55 R16 91V",
        hs_code="40111000",
        quantity=Decimal("1000"),
        unit_price=Decimal("10.00"),
        unit_weight_kg=Decimal("2"),
        unit_volume_cbm=Decimal("0.055"),
    )
    po_a.lines.append(line_a)

    po_b = PurchaseOrder(
        org_id=org.id,
        po_number="PO-2026-015",
        supplier_id=mats.id,
        currency=currency,
        fx_rate=Decimal("1"),
        incoterm=Incoterm.FOB,
        order_date=today - timedelta(days=68),
    )
    line_b = PurchaseOrderLine(
        org_id=org.id,
        line_no=1,
        sku="MAT-EVA-6040-GY",
        description="EVA floor mat 60x40 cm, grey",
        hs_code="39181090",
        quantity=Decimal("500"),
        unit_price=Decimal("20.00"),
        unit_weight_kg=Decimal("5"),
        unit_volume_cbm=Decimal("0.024"),
    )
    po_b.lines.append(line_b)
    db.add_all([po_a, po_b])

    shipment = Shipment(
        org_id=org.id,
        reference="MEDUSH2604417",
        carrier_scac="MSCU",
        incoterm=Incoterm.FOB,
        origin_unlocode="CNNGB",
        destination_unlocode="FRLEH",
        etd=today - timedelta(days=42),
        eta=today - timedelta(days=5),
    )
    db.add(shipment)
    db.flush()

    # CNT1 is discharged and still on the terminal: the last free day is a few days out. CNT2 left the
    # terminal, so it carries a last free day but no demurrage risk.
    cnt1 = Container(
        org_id=org.id,
        shipment_id=shipment.id,
        container_number="MSCU4821990",
        iso_type="40HC",
        carrier_scac="MSCU",
        milestone=ContainerMilestone.DISCHARGED,
        tracking_state=TrackingState.MANUAL,
        eta=now - timedelta(days=5),
        ata=now - timedelta(days=5),
        discharged_at=now - timedelta(days=4),
        free_days_demurrage=FREE_DAYS_DEMURRAGE,
    )
    cnt2 = Container(
        org_id=org.id,
        shipment_id=shipment.id,
        container_number="TGHU7245081",
        iso_type="40HC",
        carrier_scac="MSCU",
        milestone=ContainerMilestone.GATE_OUT_FULL,
        tracking_state=TrackingState.MANUAL,
        eta=now - timedelta(days=5),
        ata=now - timedelta(days=5),
        discharged_at=now - timedelta(days=5),
        gate_out_at=now - timedelta(days=2),
        free_days_demurrage=FREE_DAYS_DEMURRAGE,
    )
    db.add_all([cnt1, cnt2])
    db.flush()

    # PO-A is split 600 / 400 over the two containers, PO-B travels whole in CNT1.
    db.add_all(
        [
            ContainerLoad(org_id=org.id, container_id=cnt1.id, po_line_id=line_a.id, quantity=Decimal("600")),
            ContainerLoad(org_id=org.id, container_id=cnt1.id, po_line_id=line_b.id, quantity=Decimal("500")),
            ContainerLoad(org_id=org.id, container_id=cnt2.id, po_line_id=line_a.id, quantity=Decimal("400")),
        ]
    )

    def cost(
        *,
        cost_type: CostType,
        amount: Decimal,
        method: AllocationMethod,
        cost_date: date,
        vendor: str,
        invoice_number: str,
        scope: CostScope,
        shipment_id: UUID | None = None,
        container_id: UUID | None = None,
    ) -> Cost:
        return Cost(
            org_id=org.id,
            scope=scope,
            shipment_id=shipment_id,
            container_id=container_id,
            cost_type=cost_type,
            amount=amount,
            currency=currency,
            fx_rate=Decimal("1"),
            fx_date=cost_date,
            fx_source="same",
            amount_base=amount,
            allocation_method=method,
            cost_date=cost_date,
            vendor=vendor,
            invoice_number=invoice_number,
        )

    costs = [
        cost(
            scope=CostScope.CONTAINER,
            container_id=cnt1.id,
            cost_type=CostType.DRAYAGE,
            amount=Decimal("300.00"),
            method=AllocationMethod.BY_VALUE,
            cost_date=today - timedelta(days=3),
            vendor="Transports Delcourt",
            invoice_number="TD-2026-0412",
        ),
        cost(
            scope=CostScope.CONTAINER,
            container_id=cnt2.id,
            cost_type=CostType.DRAYAGE,
            amount=Decimal("200.00"),
            method=AllocationMethod.BY_VALUE,
            cost_date=today - timedelta(days=2),
            vendor="Transports Delcourt",
            invoice_number="TD-2026-0413",
        ),
        cost(
            scope=CostScope.SHIPMENT,
            shipment_id=shipment.id,
            cost_type=CostType.OCEAN_FREIGHT,
            amount=Decimal("3000.00"),
            method=AllocationMethod.BY_WEIGHT,
            cost_date=today - timedelta(days=40),
            vendor="Kuehne + Nagel France",
            invoice_number="KN-26-118377",
        ),
    ]
    db.add_all(costs)
    db.flush()
    recompute_org(db, org)
    return SampleData(
        containers=[cnt1, cnt2],
        supplier_count=2,
        purchase_order_count=2,
        cost_count=len(costs),
        shipment_reference=shipment.reference,
    )
