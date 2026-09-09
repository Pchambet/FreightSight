"""Estimated against invoiced: in the landed cost report, and at month end."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domain.models import Organization


@pytest.fixture
def org(client: TestClient, db: Session, org_id: uuid.UUID) -> Organization:
    assert client.get("/api/v1/organization").status_code == 200
    organization = db.get(Organization, org_id)
    assert organization is not None
    return organization


def seed(client: TestClient) -> tuple[str, str, str]:
    """Two purchase orders in one container, 600 and 400 units at 10.00: T5's split."""
    first = client.post(
        "/api/v1/purchase-orders",
        json={
            "po_number": "PO-A",
            "currency": "EUR",
            "lines": [{"line_no": 1, "quantity": "600", "unit_price": "10.00"}],
        },
    )
    second = client.post(
        "/api/v1/purchase-orders",
        json={
            "po_number": "PO-B",
            "currency": "EUR",
            "lines": [{"line_no": 1, "quantity": "400", "unit_price": "10.00"}],
        },
    )
    assert first.status_code == 201 and second.status_code == 201
    container = client.post("/api/v1/containers", json={"container_number": "MSCU4821990"})
    container_id = str(container.json()["id"])
    loads = client.put(
        f"/api/v1/containers/{container_id}/loads",
        json=[
            {"po_line_id": first.json()["lines"][0]["id"], "quantity": "600"},
            {"po_line_id": second.json()["lines"][0]["id"], "quantity": "400"},
        ],
    )
    assert loads.status_code == 200, loads.text
    return container_id, str(first.json()["id"]), str(second.json()["id"])


def add_cost(
    client: TestClient,
    container_id: str,
    *,
    amount: str,
    status: str = "ACTUAL",
    cost_type: str = "OCEAN_FREIGHT",
    cost_date: str = "2026-03-12",
) -> dict[str, Any]:
    res = client.post(
        "/api/v1/costs",
        json={
            "scope": "CONTAINER",
            "target_id": container_id,
            "cost_type": cost_type,
            "amount": amount,
            "currency": "EUR",
            "cost_date": cost_date,
            "status": status,
        },
    )
    assert res.status_code == 201, res.text
    body: dict[str, Any] = res.json()
    return body


def landed(client: TestClient, container_id: str) -> dict[str, Any]:
    report: dict[str, Any] = client.get(f"/api/v1/landed-costs/containers/{container_id}").json()
    return report


# ---------------------------------------------------------------------------- in the landed cost


def test_the_report_separates_what_is_expected_from_what_is_invoiced(
    client: TestClient, org: Organization
) -> None:
    container_id, _, _ = seed(client)
    add_cost(client, container_id, amount="3000.00", status="ESTIMATE")
    add_cost(client, container_id, amount="275.00", cost_type="THC")

    report = landed(client, container_id)
    assert report["totals"]["estimated"] == "3000.00"
    assert report["totals"]["actual"] == "275.00"
    assert report["totals"]["allocated"] == "3275.00"
    assert report["by_cost_type_detail"]["OCEAN_FREIGHT"] == {"estimated": "3000.00", "actual": "0.00"}
    assert report["by_cost_type_detail"]["THC"] == {"estimated": "0.00", "actual": "275.00"}
    assert report["completeness"] == "0.50"  # one of the two expected charges has arrived


def test_the_variance_is_exact_to_the_cent_on_every_line(client: TestClient, org: Organization) -> None:
    """The replaced estimate goes back through the engine, so a line's variance is a difference of
    two real allocations rather than a proportion invented afterwards."""
    container_id, _, _ = seed(client)
    estimate = add_cost(client, container_id, amount="3000.00", status="ESTIMATE")
    actual = add_cost(client, container_id, amount="3120.50")
    assert (
        client.patch(f"/api/v1/costs/{actual['id']}", json={"supersedes_cost_id": estimate["id"]}).status_code
        == 200
    )

    report = landed(client, container_id)
    assert report["totals"]["actual"] == "3120.50"
    assert report["totals"]["estimated"] == "0.00"  # the estimate is no longer standing in
    assert report["totals"]["variance"] == "120.50"
    assert report["completeness"] == "1.00"

    # 60/40 by value, and the two line variances add back up to the whole
    variances = sorted(line["variance"] for line in report["lines"])
    assert variances == ["48.20", "72.30"]
    assert sum(map(float, variances)) == 120.50


def test_a_cheaper_invoice_is_a_negative_variance(client: TestClient, org: Organization) -> None:
    container_id, _, _ = seed(client)
    estimate = add_cost(client, container_id, amount="3000.00", status="ESTIMATE")
    actual = add_cost(client, container_id, amount="2880.00")
    client.patch(f"/api/v1/costs/{actual['id']}", json={"supersedes_cost_id": estimate["id"]})
    assert landed(client, container_id)["totals"]["variance"] == "-120.00"


def test_completeness_counts_types_not_amounts(client: TestClient, org: Organization) -> None:
    """A large freight invoice must not make a missing customs bill look like a rounding error."""
    container_id, _, _ = seed(client)
    add_cost(client, container_id, amount="3000.00")  # invoiced
    add_cost(client, container_id, amount="130.00", status="ESTIMATE", cost_type="CUSTOMS_BROKERAGE")
    add_cost(client, container_id, amount="275.00", status="ESTIMATE", cost_type="THC")
    assert landed(client, container_id)["completeness"] == "0.33"


def test_nothing_expected_yet_is_not_zero_completeness(client: TestClient, org: Organization) -> None:
    container_id, _, _ = seed(client)
    assert landed(client, container_id)["completeness"] is None


# ---------------------------------------------------------------------------- at month end


def test_the_month_report_groups_by_charge_and_by_order(client: TestClient, org: Organization) -> None:
    container_id, _, _ = seed(client)
    freight_estimate = add_cost(client, container_id, amount="3000.00", status="ESTIMATE")
    freight = add_cost(client, container_id, amount="3120.50", cost_date="2026-03-12")
    client.patch(f"/api/v1/costs/{freight['id']}", json={"supersedes_cost_id": freight_estimate["id"]})

    thc_estimate = add_cost(client, container_id, amount="275.00", status="ESTIMATE", cost_type="THC")
    thc = add_cost(client, container_id, amount="262.00", cost_type="THC", cost_date="2026-03-20")
    client.patch(f"/api/v1/costs/{thc['id']}", json={"supersedes_cost_id": thc_estimate["id"]})

    report = client.get("/api/v1/reports/variance", params={"period": "2026-03"}).json()
    assert report["pairs"] == 2
    assert report["estimated"] == "3275.00"
    assert report["actual"] == "3382.50"
    assert report["variance"] == "107.50"

    by_type = {row["key"]: row for row in report["by_cost_type"]}
    assert by_type["OCEAN_FREIGHT"]["variance"] == "120.50"
    assert by_type["THC"]["variance"] == "-13.00"

    by_po = {row["label"]: row for row in report["by_purchase_order"]}
    assert by_po["PO-A"]["variance"] == "64.50"  # 60 % of 107.50
    assert by_po["PO-B"]["variance"] == "43.00"
    assert sorted(by_po) == ["PO-A", "PO-B"]


def test_only_the_month_asked_for_is_counted(client: TestClient, org: Organization) -> None:
    container_id, _, _ = seed(client)
    estimate = add_cost(client, container_id, amount="3000.00", status="ESTIMATE")
    actual = add_cost(client, container_id, amount="3120.50", cost_date="2026-04-02")
    client.patch(f"/api/v1/costs/{actual['id']}", json={"supersedes_cost_id": estimate["id"]})

    march = client.get("/api/v1/reports/variance", params={"period": "2026-03"}).json()
    assert march["pairs"] == 0 and march["variance"] == "0.00"
    april = client.get("/api/v1/reports/variance", params={"period": "2026-04"}).json()
    assert april["pairs"] == 1 and april["variance"] == "120.50"


def test_an_invoice_nobody_forecast_is_not_an_overrun(client: TestClient, org: Organization) -> None:
    """Counting an unforecast invoice as a 100 % overrun would be a lie by arithmetic."""
    container_id, _, _ = seed(client)
    add_cost(client, container_id, amount="3120.50", cost_date="2026-03-12")
    report = client.get("/api/v1/reports/variance", params={"period": "2026-03"}).json()
    assert report["pairs"] == 0
    assert report["by_cost_type"] == []


def test_a_malformed_period_is_refused(client: TestClient, org: Organization) -> None:
    assert client.get("/api/v1/reports/variance", params={"period": "March"}).status_code == 422
