"""End-to-end through the API against a real Postgres."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

FIXTURES = Path(__file__).parent / "fixtures"


def _upload(
    client: TestClient, name: str = "legacy_po_container.csv", content: bytes | None = None
) -> dict[str, Any]:
    data = content if content is not None else (FIXTURES / name).read_bytes()
    res = client.post("/api/purchase-orders/upload", files={"file": (name, data, "text/csv")})
    assert res.status_code == 200, res.text
    return dict(res.json())


def test_health_endpoints(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").status_code == 200


def test_missing_org_header_is_400(client: TestClient) -> None:
    res = client.get("/api/containers", headers={"X-Org-Id": ""})
    assert res.status_code in (400, 422)


def test_import_then_landed_costs_sum_to_100_percent(client: TestClient) -> None:
    summary = _upload(client)
    assert summary["rows_processed"] == 3
    assert summary["rows_skipped"] == []
    assert summary["purchase_orders_created"] == 3
    assert summary["containers_created"] == 2
    assert summary["containers_linked"] == 3

    containers = {c["container_number"]: c for c in client.get("/api/containers").json()}
    assert set(containers) == {"MSCU1234567", "CMAU9876543"}
    mscu = containers["MSCU1234567"]
    assert mscu["status"] == "PENDING"

    for cost_type, amount in (("OCEAN_FREIGHT", "1500.00"), ("CUSTOMS", "300.00")):
        res = client.post(
            f"/api/containers/{mscu['id']}/costs",
            json={"cost_type": cost_type, "amount": amount, "currency": "EUR"},
        )
        assert res.status_code == 201, res.text
        assert res.json()["amount"] == amount

    report = client.get(f"/api/containers/{mscu['id']}/landed-costs").json()
    assert report["base_currency"] == "EUR"
    assert report["total_additional_costs"] == "1800.00"
    assert report["total_allocated"] == "1800.00"
    assert report["unallocated"] == "0.00"
    # legacy 100 % + 50 % is refused as manual split; falls back to value with a warning
    assert report["allocation_method"] == "BY_VALUE"
    assert [w["code"] for w in report["warnings"]] == ["DEPRECATED_ALLOCATION_PCT"]
    by_po = {b["po_number"]: b for b in report["breakdown"]}
    assert by_po["PO-2026-001"]["allocated_costs"] == "1076.57"
    assert by_po["PO-2026-002"]["allocated_costs"] == "723.43"
    assert by_po["PO-2026-001"]["true_landed_cost"] == "13577.07"
    assert by_po["PO-2026-002"]["true_landed_cost"] == "9123.43"


def test_cost_in_foreign_currency_is_refused(client: TestClient) -> None:
    _upload(client)
    mscu = next(c for c in client.get("/api/containers").json() if c["container_number"] == "MSCU1234567")
    res = client.post(
        f"/api/containers/{mscu['id']}/costs",
        json={"cost_type": "DRAYAGE", "amount": "10.00", "currency": "USD"},
    )
    assert res.status_code == 422
    assert "base currency" in res.json()["detail"]


def test_float_amount_is_quantized_and_negative_refused(client: TestClient) -> None:
    _upload(client)
    mscu = next(c for c in client.get("/api/containers").json() if c["container_number"] == "MSCU1234567")
    res = client.post(
        f"/api/containers/{mscu['id']}/costs", json={"cost_type": "DRAYAGE", "amount": -5, "currency": "EUR"}
    )
    assert res.status_code == 422
    assert res.json()["errors"][0]["field"] == "amount"


def test_reimport_is_idempotent(client: TestClient) -> None:
    first = _upload(client)
    second = _upload(client)
    assert second["purchase_orders_created"] == 0
    assert second["containers_created"] == 0
    assert second["containers_linked"] == 0
    assert first["rows_processed"] == second["rows_processed"] == 3
    assert len(client.get("/api/containers").json()) == 2


def test_import_with_zero_valid_rows_is_422(client: TestClient) -> None:
    res = client.post(
        "/api/purchase-orders/upload",
        files={"file": ("bad.csv", b"po_number,total_value\n,10\n,20\n", "text/csv")},
    )
    assert res.status_code == 422
    body = res.json()
    assert body["code"] == "NO_VALID_ROWS"
    assert len(body["rows_skipped"]) == 2


def test_orgs_do_not_see_each_other(client: TestClient) -> None:
    _upload(client)
    other = {"X-Org-Id": str(uuid.uuid4())}
    assert client.get("/api/containers", headers=other).json() == []
    mscu = next(c for c in client.get("/api/containers").json() if c["container_number"] == "MSCU1234567")
    assert client.get(f"/api/containers/{mscu['id']}/landed-costs", headers=other).status_code == 404


def test_manual_status_update(client: TestClient) -> None:
    _upload(client)
    mscu = next(c for c in client.get("/api/containers").json() if c["container_number"] == "MSCU1234567")
    res = client.patch(f"/api/containers/{mscu['id']}", json={"status": "IN_TRANSIT", "carrier": "MSC"})
    assert res.status_code == 200
    assert res.json()["status"] == "IN_TRANSIT"
    assert res.json()["carrier"] == "MSC"


def test_upload_invoice_is_honest_501(client: TestClient) -> None:
    _upload(client)
    mscu = next(c for c in client.get("/api/containers").json() if c["container_number"] == "MSCU1234567")
    res = client.post(
        f"/api/containers/{mscu['id']}/upload-invoice",
        files={"file": ("inv.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert res.status_code == 501
    assert res.json()["code"] == "NOT_IMPLEMENTED"
    # and it wrote nothing
    assert client.get(f"/api/containers/{mscu['id']}/landed-costs").json()["raw_costs"] == []


def test_container_create_validates_iso_number(client: TestClient) -> None:
    assert client.post("/api/containers", json={"container_number": "nope"}).status_code == 422
    res = client.post("/api/containers", json={"container_number": "mscu1234567", "carrier": "MSC"})
    assert res.status_code == 201
    assert res.json()["container_number"] == "MSCU1234567"
    assert client.post("/api/containers", json={"container_number": "MSCU1234567"}).status_code == 409
