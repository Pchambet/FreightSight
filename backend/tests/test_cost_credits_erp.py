"""A refund on a cost already in the customer's ERP: their books hold the old figure, and it is said."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_erp_landed_cost import (
    DOCUMENT,
    WritableOdoo,
    connect,
    erp_key,  # noqa: F401 - the ERP's encryption key, for every test here
    preview,
    seed_container,
    validate_and_forget,
)

from app.domain.models import Organization


@pytest.fixture
def org(client: TestClient, db: Session, org_id: uuid.UUID) -> Organization:
    assert client.get("/api/v1/organization").status_code == 200
    organization = db.get(Organization, org_id)
    assert organization is not None
    return organization


def test_a_credit_on_a_cost_pushed_and_validated_shows_as_a_changed_amount(
    client: TestClient, org: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    odoo = WritableOdoo()
    connect(client, odoo, monkeypatch)
    container_id = seed_container(client)
    push = client.post(f"/api/v1/containers/{container_id}/erp/landed-cost")
    assert push.status_code == 201, push.text
    odoo.documents[push.json()["odoo_id"]]["state"] = "done"

    (cost,) = client.get(f"/api/v1/landed-costs/containers/{container_id}").json()["costs"]
    res = client.post(
        f"/api/v1/costs/{cost['id']}/credits",
        json={"amount": "266.67", "credit_number": "AV-2026-07", "credit_date": "2026-04-02"},
    )
    assert res.status_code == 201, res.text

    (changed,) = [b for b in preview(client, container_id)["blockers"] if b["code"] == "pushed_cost_changed"]
    assert changed["params"]["existing"] == DOCUMENT
    assert "2766.67 → 2500.00" in changed["params"]["changes"]

    # forgotten with a reason, the next push carries the refund alone, as a negative adjustment
    validate_and_forget(client, odoo, container_id, push.json())
    body = preview(client, container_id)
    assert body["total"] == "-266.67"
