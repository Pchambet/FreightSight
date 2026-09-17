"""A landed-cost report shared by link: a frozen snapshot, opened by its token and by nothing else."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.tenancy import set_current_org
from app.domain.models import SharedReport
from app.domain.shares.service import hash_token, open_by_token

PUBLIC = "/api/v1/public/shared-reports"
NOBODY = {"X-Org-Id": ""}  # the public page sends no organization at all


@pytest.fixture
def sample(client: TestClient) -> dict[str, Any]:
    res = client.post("/api/v1/organization/sample-data")
    assert res.status_code == 201, res.text
    body: dict[str, Any] = res.json()
    return body


def share(client: TestClient, container_id: str, **body: int) -> dict[str, Any]:
    res = client.post(f"/api/v1/containers/{container_id}/share", json=body)
    assert res.status_code == 201, res.text
    created: dict[str, Any] = res.json()
    return created


def test_the_link_opens_the_report_as_it_stood_and_a_later_cost_does_not_move_it(
    client: TestClient, sample: dict[str, Any]
) -> None:
    box = sample["container_ids"][0]
    live = client.get(f"/api/v1/landed-costs/containers/{box}").json()
    created = share(client, box)
    assert created["path"] == f"/r/{created['token']}" and len(created["token"]) >= 40

    late = client.post(
        "/api/v1/costs",
        json={"scope": "CONTAINER", "target_id": box, "cost_type": "INSPECTION", "amount": "145.00",
              "currency": "EUR", "cost_date": "2026-09-10"},
    )  # fmt: skip
    assert late.status_code == 201, late.text
    assert client.get(f"/api/v1/landed-costs/containers/{box}").json()["totals"] != live["totals"]

    opened = client.get(f"{PUBLIC}/{created['token']}", headers=NOBODY)
    assert opened.status_code == 200, opened.text
    assert opened.headers["cache-control"] == "no-store" and "noindex" in opened.headers["x-robots-tag"]
    body = opened.json()
    assert body["report"]["totals"] == live["totals"]  # the figure that was sent, not today's
    assert body["report"]["lines"] == live["lines"]
    assert (body["subject_type"], body["subject_label"]) == ("container", "MSCU4821990")
    assert body["shipment_reference"] == "MEDUSH2604417" and body["locale"] == "fr"
    assert body["sample_data"] is True  # sent from a demo company: the document has to say so
    assert body["issuer"]["name"]


def test_an_order_can_be_shared_too(client: TestClient, sample: dict[str, Any]) -> None:
    order = next(
        po for po in client.get("/api/v1/purchase-orders").json() if po["po_number"] == "PO-2026-014"
    )
    created = client.post(f"/api/v1/purchase-orders/{order['id']}/share", json={"expires_in_days": 7})
    assert created.status_code == 201, created.text
    body = client.get(f"{PUBLIC}/{created.json()['token']}", headers=NOBODY).json()
    assert (body["subject_type"], body["subject_label"]) == ("purchase_order", "PO-2026-014")
    assert body["report"]["totals"]["fob"] == "27300.00"


def test_the_sender_sees_that_it_was_read_and_can_take_the_link_back(
    client: TestClient, sample: dict[str, Any]
) -> None:
    box = sample["container_ids"][0]
    created = share(client, box, expires_in_days=90)
    for _ in range(3):
        assert client.get(f"{PUBLIC}/{created['token']}", headers=NOBODY).status_code == 200
    (listed,) = client.get(f"/api/v1/containers/{box}/shares").json()
    assert (listed["status"], listed["view_count"]) == ("active", 3)
    assert listed["last_viewed_at"] is not None and "token" not in listed

    assert client.delete(f"/api/v1/shares/{created['id']}").status_code == 204
    gone = client.get(f"{PUBLIC}/{created['token']}", headers=NOBODY)
    assert gone.status_code == 404 and gone.json()["code"] == "SHARE_NOT_FOUND"
    (listed,) = client.get(f"/api/v1/containers/{box}/shares").json()
    assert (listed["status"], listed["view_count"]) == ("revoked", 3)
    actions = [
        e["action"] for e in client.get("/api/v1/audit-log", params={"entity_id": box}).json()["entries"]
    ]
    assert actions[:2] == ["share.revoked", "container.shared"]


def test_unknown_expired_and_revoked_are_one_and_the_same_answer(
    client: TestClient, db: Session, sample: dict[str, Any]
) -> None:
    created = share(client, sample["container_ids"][0], expires_in_days=1)
    row = db.scalar(select(SharedReport).where(SharedReport.id == uuid.UUID(created["id"])))
    assert row is not None
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    answers = [
        client.get(f"{PUBLIC}/{created['token']}", headers=NOBODY),  # expired
        client.get(f"{PUBLIC}/{'x' * 43}", headers=NOBODY),  # never existed
        client.get(f"{PUBLIC}/short", headers=NOBODY),  # not even the shape of one
    ]
    assert {(a.status_code, a.json()["code"]) for a in answers} == {(404, "SHARE_NOT_FOUND")}
    (listed,) = client.get(f"/api/v1/containers/{sample['container_ids'][0]}/shares").json()
    assert (listed["status"], listed["view_count"]) == ("expired", 0)


def test_the_database_holds_no_token_only_its_hash(
    client: TestClient, db: Session, sample: dict[str, Any]
) -> None:
    created = share(client, sample["container_ids"][0])
    row = db.execute(text("SELECT * FROM shared_reports")).mappings().one()
    assert row["token_hash"] == hash_token(created["token"])
    assert created["token"] not in str(dict(row))


def test_another_organization_neither_lists_nor_revokes_our_links(
    client: TestClient, sample: dict[str, Any]
) -> None:
    box = sample["container_ids"][0]
    created = share(client, box)
    theirs = {"X-Org-Id": str(uuid.uuid4())}
    assert client.get(f"/api/v1/containers/{box}/shares", headers=theirs).status_code == 404
    assert client.delete(f"/api/v1/shares/{created['id']}", headers=theirs).status_code == 404
    assert client.get(f"{PUBLIC}/{created['token']}", headers=NOBODY).status_code == 200


def test_under_the_application_role_the_token_opens_its_own_row_and_no_other(
    client: TestClient, db: Session, org_id: uuid.UUID, sample: dict[str, Any]
) -> None:
    """The door through row-level security, tried as the role production runs as: with no tenant set,
    the right token reaches its snapshot, a wrong one reaches nothing, and the table stays shut."""
    first = share(client, sample["container_ids"][0])
    share(client, sample["container_ids"][1])
    db.commit()
    db.execute(text("SET ROLE freightsight_app"))
    try:
        set_current_org(db, None)
        assert list(db.scalars(select(SharedReport))) == []  # no tenant, no token: nothing
        opened = open_by_token(db, first["token"])
        assert opened is not None and opened[0]["subject_label"] == "MSCU4821990"
        assert list(db.scalars(select(SharedReport))) == []  # and the door closed behind it
        assert open_by_token(db, "y" * 43) is None
    finally:
        db.execute(text("RESET ROLE"))
        set_current_org(db, org_id)
