"""DELETE /organization/sample-data: the demo goes, what only existed because of it goes with it, and
nothing of the user's own is ever deleted along."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pdfs import make_pdf
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models import (
    Alert,
    Container,
    ContainerLoad,
    Cost,
    CostAllocation,
    Document,
    Invoice,
    PurchaseOrder,
    PurchaseOrderLine,
    RateCard,
    SampleObject,
    Shipment,
    SkuCostHistory,
    Supplier,
)
from app.jobs import handlers

EVERYTHING = (
    Alert, Container, ContainerLoad, Cost, CostAllocation, Document, Invoice, PurchaseOrder,
    PurchaseOrderLine, RateCard, SampleObject, Shipment, SkuCostHistory, Supplier,
)  # fmt: skip


def rows(db: Session) -> dict[str, int]:
    db.expire_all()
    return {m.__tablename__: db.scalar(select(func.count()).select_from(m)) or 0 for m in EVERYTHING}


@pytest.mark.parametrize("profile", ["reference", "history"])
def test_a_loaded_demo_is_taken_away_whole(client: TestClient, db: Session, profile: str) -> None:
    assert client.get("/api/v1/organization").json()["has_sample_data"] is False
    assert client.post("/api/v1/organization/sample-data", params={"profile": profile}).status_code == 201
    assert client.get("/api/v1/organization").json()["has_sample_data"] is True
    loaded = rows(db)
    assert loaded["containers"] > 0 and loaded["sample_objects"] > 0

    res = client.delete("/api/v1/organization/sample-data")
    assert res.status_code == 200, res.text
    deleted = res.json()["deleted"]
    assert deleted["containers"] == loaded["containers"] and deleted["costs"] == loaded["costs"]
    assert rows(db) == dict.fromkeys(loaded, 0)
    assert client.get("/api/v1/organization").json()["has_sample_data"] is False
    # and the organization is as empty as before: the demo can be loaded again
    assert client.post("/api/v1/organization/sample-data").status_code == 201


def test_a_cost_typed_on_a_demo_container_goes_with_the_container(client: TestClient, db: Session) -> None:
    sample = client.post("/api/v1/organization/sample-data").json()
    typed = client.post(
        "/api/v1/costs",
        json={"scope": "CONTAINER", "target_id": sample["container_ids"][0], "cost_type": "INSPECTION",
              "amount": "145.00", "currency": "EUR", "cost_date": "2026-09-10"},
    )  # fmt: skip
    assert typed.status_code == 201, typed.text
    assert client.delete("/api/v1/organization/sample-data").status_code == 200
    assert rows(db)["costs"] == 0


def own_order(client: TestClient) -> dict[str, Any]:
    res = client.post(
        "/api/v1/purchase-orders",
        json={"po_number": "PO-MINE", "currency": "EUR",
              "lines": [{"line_no": 1, "sku": "MINE-1", "quantity": "10", "unit_price": "5"}]},
    )  # fmt: skip
    assert res.status_code == 201, res.text
    body: dict[str, Any] = res.json()
    return body


def test_my_own_goods_in_a_demo_container_stop_the_deletion_by_name(client: TestClient, db: Session) -> None:
    sample = client.post("/api/v1/organization/sample-data").json()
    box = sample["container_ids"][0]
    existing = client.get(f"/api/v1/containers/{box}/loads").json()
    mine = own_order(client)["lines"][0]["id"]
    loads = [{"po_line_id": ld["po_line_id"], "quantity": ld["quantity"]} for ld in existing]
    loads.append({"po_line_id": mine, "quantity": "10"})
    assert client.put(f"/api/v1/containers/{box}/loads", json=loads).status_code == 200
    before = rows(db)

    res = client.delete("/api/v1/organization/sample-data")
    assert res.status_code == 409 and res.json()["code"] == "SAMPLE_DATA_IN_USE"
    assert res.json()["errors"] == [
        {"field": "MSCU4821990", "code": "OWN_LOAD_ON_SAMPLE", "message": "OWN_LOAD_ON_SAMPLE"}
    ]
    assert rows(db) == before  # refused means nothing moved


def test_my_own_data_next_to_the_demo_is_left_alone(client: TestClient, db: Session) -> None:
    client.post("/api/v1/organization/sample-data")
    own_order(client)
    own_box = client.post("/api/v1/containers", json={"container_number": "TCLU1234565"})
    assert own_box.status_code == 201, own_box.text
    client.post("/api/v1/products", json={"sku": "TYR-20555R16-91V", "sale_price": "39.90"})

    assert client.delete("/api/v1/organization/sample-data").status_code == 200
    assert [po["po_number"] for po in client.get("/api/v1/purchase-orders").json()] == ["PO-MINE"]
    assert [c["container_number"] for c in client.get("/api/v1/containers").json()] == ["TCLU1234565"]
    assert len(client.get("/api/v1/products").json()["products"]) == 1  # a product sheet typed by hand stays


def test_a_cost_from_an_invoice_i_uploaded_stops_the_deletion(
    client: TestClient, db: Session, org_id: uuid.UUID
) -> None:
    sample = client.post("/api/v1/organization/sample-data").json()
    text = ["MON TRANSITAIRE SAS", "FACTURE N° MT-2026-77", "Date : 10/09/2026", "Conteneur MSCU4821990"]
    pdf = make_pdf([*text, "Scanner douane        145,00", "Total HT     145,00"])
    uploaded = client.post("/api/v1/invoices", files={"file": ("mt.pdf", pdf, "application/pdf")})
    assert uploaded.status_code == 201, uploaded.text
    invoice_id = uploaded.json()["id"]
    handlers.extract_invoice(db, org_id, uuid.UUID(invoice_id))  # what the worker does, called directly
    detail = client.get(f"/api/v1/invoices/{invoice_id}").json()
    (line,) = detail["lines"]
    patched = client.patch(
        f"/api/v1/invoices/{invoice_id}/lines/{line['id']}",
        json={"accepted": True, "cost_type": "INSPECTION", "scope": "CONTAINER",
              "target_id": sample["container_ids"][0]},
    )  # fmt: skip
    assert patched.status_code == 200, patched.text
    assert client.post(f"/api/v1/invoices/{invoice_id}/confirm").status_code == 200

    res = client.delete("/api/v1/organization/sample-data")
    assert res.status_code == 409
    assert {
        "field": "MSCU4821990",
        "code": "OWN_COST_ON_SAMPLE",
        "message": "OWN_COST_ON_SAMPLE",
    } in res.json()["errors"]


def test_there_is_nothing_to_delete_in_an_organization_that_never_loaded_it(client: TestClient) -> None:
    res = client.delete("/api/v1/organization/sample-data")
    assert res.status_code == 404 and res.json()["code"] == "NO_SAMPLE_DATA"
