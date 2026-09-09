"""POST /api/v1/organization/sample-data: the demo dataset is the T5 reference case, is created once, and
never leaks between organizations."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.tenancy import set_current_org
from app.domain.models import Container, Cost, PurchaseOrder


def test_sample_data_seeds_the_reference_case(client: TestClient) -> None:
    res = client.post("/api/v1/organization/sample-data")
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["suppliers"] == 2 and body["purchase_orders"] == 2
    assert body["containers"] == 2 and body["costs"] == 3
    assert len(body["container_ids"]) == 2

    containers = {c["container_number"]: c for c in client.get("/api/v1/containers").json()}
    assert sorted(containers) == ["MSCU4821990", "TGHU7245081"]
    cnt1, cnt2 = containers["MSCU4821990"], containers["TGHU7245081"]
    assert cnt1["milestone"] == "DISCHARGED"
    assert cnt1["last_free_day"] is not None and cnt1["dnd_risk"] == "MEDIUM"
    # gated out: demurrage stopped at the terminal, detention started on the empty
    assert cnt2["last_free_day"] is not None
    assert cnt2["detention_deadline"] is not None
    assert cnt2["dnd_risk"] == "LOW"

    assert cnt1["allocated_base"] == "2766.67"
    assert cnt1["po_numbers"] == ["PO-2026-014", "PO-2026-015"]
    assert cnt1["cost_types_present"] == ["DRAYAGE", "OCEAN_FREIGHT"]

    report = client.get(f"/api/v1/landed-costs/containers/{cnt1['id']}").json()
    assert report["warnings"] == []
    assert report["totals"] == {
        "fob": "16000.00",
        "allocated": "2766.67",
        "vat": "0.00",
        "landed": "18766.67",
        "unallocated": "0.00",
        # the sample data is a set of invoices, so it is fully actual and has nothing to compare
        "estimated": "0.00",
        "actual": "2766.67",
        "variance": "0.00",
    }
    assert report["completeness"] == "1.00"
    by_po = {ln["po_number"]: ln for ln in report["lines"]}
    assert by_po["PO-2026-014"]["unit_landed_cost"] == "11.5208"
    assert by_po["PO-2026-015"]["unit_landed_cost"] == "23.7083"

    po_id = client.get("/api/v1/purchase-orders").json()[0]["id"]
    po = client.get(f"/api/v1/landed-costs/purchase-orders/{po_id}").json()
    assert po["totals"]["allocated"] == "1645.83" and po["totals"]["landed"] == "11645.83"

    integrity = client.get("/api/v1/reports/integrity").json()
    assert integrity["ok"] and integrity["costs_checked"] == 3


def test_sample_data_is_loaded_only_once(client: TestClient, db: Session) -> None:
    assert client.post("/api/v1/organization/sample-data").status_code == 201
    again = client.post("/api/v1/organization/sample-data")
    assert again.status_code == 409 and again.json()["code"] == "CONFLICT"
    assert len(client.get("/api/v1/containers").json()) == 2
    assert len(client.get("/api/v1/purchase-orders").json()) == 2
    assert len(client.get("/api/v1/costs").json()) == 3


def test_sample_data_refused_when_the_organization_already_has_data(client: TestClient) -> None:
    assert client.post("/api/v1/containers", json={"container_number": "MSCU1234567"}).status_code == 201
    res = client.post("/api/v1/organization/sample-data")
    assert res.status_code == 409
    assert len(client.get("/api/v1/containers").json()) == 1


def test_sample_data_is_isolated_per_organization(client: TestClient, db: Session, org_id: uuid.UUID) -> None:
    other = uuid.uuid4()
    assert client.post("/api/v1/organization/sample-data").status_code == 201
    assert (
        client.post("/api/v1/organization/sample-data", headers={"X-Org-Id": str(other)}).status_code == 201
    )

    for org in (org_id, other):
        containers = client.get("/api/v1/containers", headers={"X-Org-Id": str(org)}).json()
        assert len(containers) == 2

    db.execute(text("SET ROLE freightsight_app"))
    try:
        set_current_org(db, org_id)
        assert {c.org_id for c in db.scalars(select(Container))} == {org_id}
        assert {p.org_id for p in db.scalars(select(PurchaseOrder))} == {org_id}
        assert {c.org_id for c in db.scalars(select(Cost))} == {org_id}
    finally:
        db.execute(text("RESET ROLE"))
        set_current_org(db, org_id)
