"""Where an order's exchange rate comes from, and how a missing one is found again.

A rate the order file gives is kept as given, like one typed on the order; one the ECB gives says so.
An order left without a rate — the provider down when it was written — was only retried by a later
import of the same file, and the ERP sync never reads an unchanged order again: the worker now asks
the provider again on its own, and says so in the order's history.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from conftest import fake_fetcher
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.domain.fx.service import FxService
from app.domain.models import AuditLog, PurchaseOrder
from app.jobs import handlers


def imported(client: TestClient, content: bytes) -> dict[str, Any]:
    files = {"file": ("orders.csv", content, "text/csv")}
    job = client.post("/api/v1/imports", data={"kind": "PURCHASE_ORDERS"}, files=files).json()
    res = client.post(f"/api/v1/imports/{job['id']}/validate", json={"mapping": job["mapping"]})
    assert res.status_code == 200, res.text
    report = dict(res.json()["report"])
    assert client.post(f"/api/v1/imports/{job['id']}/commit", json={}).status_code == 200
    return report


def orders(client: TestClient) -> dict[str, dict[str, Any]]:
    found = {}
    for summary in client.get("/api/v1/purchase-orders").json():
        found[summary["po_number"]] = client.get(f"/api/v1/purchase-orders/{summary['id']}").json()
    return found


def test_a_rate_column_of_the_order_file_is_kept_as_given(client: TestClient) -> None:
    report = imported(
        client,
        "N° commande;Devise;Taux de change;Date de commande;Référence;Quantité;Prix unitaire\n"
        "PO-VND;VND;0,0000365;2026-09-10;A;10;100000\n"
        "PO-USD;USD;;2026-09-10;B;10;100\n".encode(),
    )
    (given,) = [w for w in report["warnings"] if w["code"] == "FX_RATE_FROM_FILE"]
    assert given["params"] == {"currency": "VND", "base_currency": "EUR", "rate": "0.0000365"}
    found = orders(client)
    vnd, usd = found["PO-VND"], found["PO-USD"]
    assert (Decimal(vnd["fx_rate"]), vnd["fx_source"], vnd["fx_date"]) == (
        Decimal("0.0000365"),
        "import",
        "2026-09-10",
    )
    assert (usd["fx_rate"], usd["fx_source"]) == ("0.92", "ecb")
    # A rate the file gave is a person's word: an edit of the order date does not look it up again.
    res = client.patch(f"/api/v1/purchase-orders/{vnd['id']}", json={"order_date": "2026-09-01"})
    assert res.status_code == 200, res.text
    assert Decimal(res.json()["fx_rate"]) == Decimal("0.0000365")


def test_a_file_stating_another_rate_replaces_it_and_the_same_rate_changes_nothing(
    client: TestClient,
) -> None:
    head = "N° commande;Devise;Taux de change;Date de commande;Référence;Quantité;Prix unitaire\n"
    imported(client, f"{head}PO-USD;USD;;2026-09-10;B;10;100\n".encode())
    report = imported(client, f"{head}PO-USD;USD;0,90;2026-09-10;B;10;100\n".encode())
    assert [w["code"] for w in report["warnings"] if w["code"].startswith("FX_")] == ["FX_RATE_FROM_FILE"]
    usd = orders(client)["PO-USD"]
    assert (usd["fx_rate"], usd["fx_source"]) == ("0.9", "import")
    report = imported(client, f"{head}PO-USD;USD;0,90;2026-09-10;B;10;100\n".encode())
    assert not [w for w in report["warnings"] if w["code"].startswith("FX_")]


def test_the_worker_gives_a_missing_rate_once_the_provider_has_it(
    client: TestClient, db: Session, org_id: UUID
) -> None:
    body = {"po_number": "PO-USD", "currency": "USD", "order_date": "2026-09-10", "fx_rate": "1",
            "lines": [{"line_no": 1, "sku": "A", "quantity": "10", "unit_price": "100"}]}  # fmt: skip
    usd = client.post("/api/v1/purchase-orders", json=body).json()
    xts = client.post("/api/v1/purchase-orders", json={**body, "po_number": "PO-XTS"}).json()
    # Both written while the provider was down: no rate, no source, and none held for their day.
    missing = {"fx_rate": None, "fx_date": None, "fx_source": None}
    db.execute(update(PurchaseOrder).where(PurchaseOrder.id.in_([usd["id"], xts["id"]])).values(**missing))
    db.execute(update(PurchaseOrder).where(PurchaseOrder.id == UUID(xts["id"])).values(currency="XTS"))
    db.flush()

    assert handlers.resolve_missing_rates(db, fx=FxService(lambda *_: None)) == 0  # still down
    assert handlers.resolve_missing_rates(db, fx=FxService(fake_fetcher)) == 1

    found = orders(client)
    assert (found["PO-USD"]["fx_rate"], found["PO-USD"]["fx_source"]) == ("0.92", "ecb")
    assert found["PO-USD"]["fx_date"] == date(2026, 9, 10).isoformat()
    assert found["PO-XTS"]["fx_rate"] is None  # a currency the provider does not quote stays missing
    (summary,) = [s for s in client.get("/api/v1/purchase-orders").json() if s["po_number"] == "PO-USD"]
    assert summary["fob_base"] == "920.00"
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "purchase_order.updated"))
    assert entry is not None and entry.org_id == org_id and entry.actor_user_id is None
    assert entry.entity_id == UUID(usd["id"])
    assert entry.after == {"fx_rate": "0.92", "fx_date": "2026-09-10", "fx_source": "ecb"}


def test_the_audit_preparation_names_the_orders_still_at_a_defaulted_rate(
    client: TestClient, db: Session
) -> None:
    """The orders the import wrote at 1 before a missing rate was left empty: nothing else names them."""
    body = {"po_number": "PO-OLD", "currency": "USD", "fx_rate": "1",
            "lines": [{"line_no": 1, "sku": "A", "quantity": "10", "unit_price": "100"}]}  # fmt: skip
    po = client.post("/api/v1/purchase-orders", json=body).json()
    db.execute(update(PurchaseOrder).where(PurchaseOrder.id == UUID(po["id"])).values(fx_source=None))
    db.flush()
    box = client.post("/api/v1/containers", json={"container_number": "MSCU1234567"}).json()
    landed = {"discharged_at": "2026-09-15T08:00:00+00:00", "milestone": "DISCHARGED"}
    assert client.patch(f"/api/v1/containers/{box['id']}", json=landed).status_code == 200
    loads = [{"po_line_id": po["lines"][0]["id"], "quantity": "10"}]
    assert client.put(f"/api/v1/containers/{box['id']}/loads", json=loads).status_code == 200
    period = {"period_from": "2026-09-01", "period_to": "2026-09-30"}

    def item() -> list[dict[str, Any]]:
        found = client.get("/api/v1/reports/audit/preparation", params=period).json()["items"]
        return [i for i in found if i["code"] == "ORDERS_RATE_UNCONFIRMED"]

    (flagged,) = item()
    assert (flagged["severity"], flagged["count"]) == ("limits", 1)
    assert flagged["examples"] == [{"kind": "purchase_order", "id": po["id"], "label": "PO-OLD"}]
    # A person confirms the rate as it stands: it now has a source, and is no longer to be checked.
    assert client.patch(f"/api/v1/purchase-orders/{po['id']}", json={"fx_rate": "1"}).status_code == 200
    assert item() == []
