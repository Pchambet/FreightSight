"""Writing our landed cost back into Odoo: what would be written, and what stops it.

The fixtures are responses captured from a real Odoo 17 running the `stock_landed_costs` module,
against a receipt this session created, valued FIFO with automated valuation.
"""

from __future__ import annotations

import base64
import json
import uuid
import xmlrpc.client
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.tenancy import set_current_org
from app.domain.models import ErpPush, Organization

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "odoo" / "landed_cost.json").read_text())
ERP_KEY = base64.b64encode(b"e" * 32).decode()

PICKING_ID = 22
MOVE_ID = 40
PO_NUMBER = "P00012"
SKU = "TYR-20555R16"


@pytest.fixture(autouse=True)
def erp_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    import os

    from app.core.settings import get_settings

    monkeypatch.setenv("ERP_ENCRYPTION_KEY", ERP_KEY)
    monkeypatch.setenv("DATABASE_URL", os.environ.get("DATABASE_URL", "postgresql+psycopg://x@x/x"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def org(client: TestClient, db: Session, org_id: uuid.UUID) -> Organization:
    assert client.get("/api/v1/organization").status_code == 200
    organization = db.get(Organization, org_id)
    assert organization is not None
    return organization


class WritableOdoo:
    """An Odoo that answers the write-back calls from the captured responses."""

    def __init__(self, *, valued: bool = True, receipts: int = 1, fail_create: bool = False) -> None:
        self.valued = valued
        self.receipts = receipts
        self.fail_create = fail_create
        self.created: list[dict[str, Any]] = []
        self.written: list[tuple[int, dict[str, Any]]] = []

    def proxy(self, url: str) -> Any:
        return _Common() if url.endswith("/common") else _Models(self)


class _Common:
    def version(self) -> dict[str, str]:
        return {"server_version": "17.0-20260908"}

    def authenticate(self, db: str, login: str, password: str, ctx: dict[str, Any]) -> int:
        return 2


class _Models:
    def __init__(self, odoo: WritableOdoo) -> None:
        self.odoo = odoo

    def execute_kw(
        self, db: str, uid: int, password: str, model: str, method: str, args: list[Any], kwargs: Any
    ) -> Any:
        match (model, method):
            case ("res.users", "read"):
                return [{"id": 2, "name": "Mitchell Admin", "company_id": [1, "YourCompany"]}]
            case ("purchase.order", "search_read"):
                return FIXTURE["purchase_orders"]
            case ("stock.picking", "search_read"):
                pickings = FIXTURE["pickings"]
                if self.odoo.receipts == 0:
                    return []
                if self.odoo.receipts > 1:
                    second = dict(pickings[0])
                    second["id"], second["name"] = 23, "WH/IN/00008"
                    return [*pickings, second]
                return pickings
            case ("stock.move", "search_read"):
                return FIXTURE["moves"]
            case ("purchase.order.line", "read"):
                return FIXTURE["purchase_order_lines"]
            case ("product.product", "read"):
                if self.odoo.valued:
                    return FIXTURE["products_valued"]
                # The same product the receipt actually moves, carrying the valuation the demo
                # products really have. Returning the captured "Large Desk" instead would answer
                # about a product this receipt never mentions, and the blocker would name nobody.
                unvalued = FIXTURE["products_unvalued"][0]
                return [
                    {
                        **product,
                        "valuation": unvalued["valuation"],
                        "cost_method": unvalued["cost_method"],
                    }
                    for product in FIXTURE["products_valued"]
                ]
            case ("product.product", "search"):
                return [p["id"] for p in FIXTURE["landed_cost_products"]]
            case ("account.journal", "search"):
                return [j["id"] for j in FIXTURE["journals"]]
            case ("stock.landed.cost", "create"):
                if self.odoo.fail_create:
                    raise xmlrpc.client.Fault(
                        1, "Traceback...\nUserError: Please configure Stock Valuation Account"
                    )
                self.odoo.created.append(args[0])
                return 2
            case ("stock.landed.cost", "compute_landed_cost"):
                return True
            case ("stock.landed.cost", "read"):
                return FIXTURE["landed_cost_read"]
            case ("stock.valuation.adjustment.lines", "search_read"):
                return FIXTURE["adjustments"]
            case ("stock.valuation.adjustment.lines", "write"):
                self.odoo.written.append((args[0][0], args[1]))
                return True
        raise AssertionError(f"unexpected call {model}.{method}")  # pragma: no cover


def connect(client: TestClient, odoo: WritableOdoo, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.adapters.erp import odoo as odoo_module

    monkeypatch.setattr(odoo_module, "_default_proxy", odoo.proxy)
    res = client.post(
        "/api/v1/erp/connection",
        json={
            "kind": "ODOO",
            "url": "https://erp.example.test",
            "database": "fstest",
            "login": "admin",
            "api_key": "the-api-key",
        },
    )
    assert res.status_code == 201, res.text


def seed_container(client: TestClient, *, invoiced: bool = True) -> str:
    """One container of the SKU Odoo received, with an invoiced ocean freight on it."""
    po = client.post(
        "/api/v1/purchase-orders",
        json={
            "po_number": PO_NUMBER,
            "currency": "EUR",
            "lines": [{"line_no": 1, "sku": SKU, "quantity": "100", "unit_price": "10.00"}],
        },
    )
    assert po.status_code == 201, po.text
    container = client.post("/api/v1/containers", json={"container_number": "MSCU4821990"})
    container_id = str(container.json()["id"])
    loads = client.put(
        f"/api/v1/containers/{container_id}/loads",
        json=[{"po_line_id": po.json()["lines"][0]["id"], "quantity": "100"}],
    )
    assert loads.status_code == 200, loads.text
    if invoiced:
        cost = client.post(
            "/api/v1/costs",
            json={
                "scope": "CONTAINER",
                "target_id": container_id,
                "cost_type": "OCEAN_FREIGHT",
                "amount": "2766.67",
                "currency": "EUR",
                "cost_date": "2026-03-12",
                "invoice_number": "FA-2026-0912",
                "vendor": "Transitex",
            },
        )
        assert cost.status_code == 201, cost.text
    return container_id


def preview(client: TestClient, container_id: str) -> dict[str, Any]:
    res = client.get(f"/api/v1/containers/{container_id}/erp/landed-cost/preview")
    assert res.status_code == 200, res.text
    body: dict[str, Any] = res.json()
    return body


# ---------------------------------------------------------------------------- the preview


def test_the_preview_shows_the_document_before_it_exists(
    client: TestClient, org: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    odoo = WritableOdoo()
    connect(client, odoo, monkeypatch)
    container_id = seed_container(client)

    body = preview(client, container_id)
    assert body["pushable"] is True
    assert body["blockers"] == []
    assert body["receipt_name"] == "WH/IN/00007"
    assert body["total"] == "2766.67"
    (cost,) = body["costs"]
    assert cost["label"] == "Ocean Freight — invoice FA-2026-0912 — Transitex"
    (line,) = cost["lines"]
    assert line["move_id"] == MOVE_ID
    assert line["sku"] == SKU
    assert line["amount"] == "2766.67"
    assert odoo.created == []  # a preview writes nothing


def test_without_a_connection_the_preview_says_so(client: TestClient, org: Organization) -> None:
    container_id = seed_container(client)
    body = preview(client, container_id)
    assert body["pushable"] is False
    assert [b["code"] for b in body["blockers"]] == ["no_erp_connection"]


def test_an_estimate_is_not_pushed(
    client: TestClient, org: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An estimate is ours to hold; it has no business in someone's accounts."""
    connect(client, WritableOdoo(), monkeypatch)
    container_id = seed_container(client, invoiced=False)
    client.post(
        "/api/v1/costs",
        json={
            "scope": "CONTAINER",
            "target_id": container_id,
            "cost_type": "OCEAN_FREIGHT",
            "amount": "3000.00",
            "currency": "EUR",
            "cost_date": "2026-03-01",
            "status": "ESTIMATE",
        },
    )
    body = preview(client, container_id)
    assert "no_actual_costs" in [b["code"] for b in body["blockers"]]
    assert body["costs"] == []


def test_a_product_odoo_cannot_value_stops_the_push(
    client: TestClient, org: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Odoo refuses a landed cost on a standard-costed product at validation — long after we would
    have written it. It is refused here instead, with the reason."""
    connect(client, WritableOdoo(valued=False), monkeypatch)
    container_id = seed_container(client)

    body = preview(client, container_id)
    assert body["pushable"] is False
    blocker = next(b for b in body["blockers"] if b["code"] == "not_valued")
    assert "automated valuation" in blocker["message"]
    assert "FIFO or average" in blocker["message"]
    assert blocker["params"] == {"products": "FS Tyre 205/55R16"}


def test_recoverable_vat_never_reaches_the_erp(
    client: TestClient, org: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Import VAT is allocated for the cash view and got back from the state. Pushing it would
    inflate the customer's stock valuation by a tax they do not bear."""
    connect(client, WritableOdoo(), monkeypatch)
    container_id = seed_container(client)
    vat = client.post(
        "/api/v1/costs",
        json={
            "scope": "CONTAINER",
            "target_id": container_id,
            "cost_type": "IMPORT_VAT",
            "amount": "553.33",
            "currency": "EUR",
            "cost_date": "2026-03-12",
            "invoice_number": "TVA-2026-0912",
        },
    )
    assert vat.status_code == 201, vat.text

    body = preview(client, container_id)
    assert body["pushable"] is True
    assert [cost["label"] for cost in body["costs"]] == ["Ocean Freight — invoice FA-2026-0912 — Transitex"]
    assert body["total"] == "2766.67"  # the freight alone, not 3320.00


def test_no_receipt_means_nothing_to_attach_to(
    client: TestClient, org: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect(client, WritableOdoo(receipts=0), monkeypatch)
    container_id = seed_container(client)
    body = preview(client, container_id)
    assert [b["code"] for b in body["blockers"]] == ["no_receipt"]
    assert "received there first" in body["blockers"][0]["message"]
    assert body["blockers"][0]["params"] == {"po_numbers": PO_NUMBER}


def test_several_receipts_are_refused_rather_than_guessed(
    client: TestClient, org: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A partial delivery is a real case, and splitting our costs across two receipts is a decision
    nobody has made yet."""
    connect(client, WritableOdoo(receipts=2), monkeypatch)
    container_id = seed_container(client)
    body = preview(client, container_id)
    assert body["pushable"] is False
    blocker = body["blockers"][0]
    # Its own code: a screen cannot write "no receipt for P00012" and "2 receipts match" from
    # the same key, and it is the code the front translates on.
    assert blocker["code"] == "multiple_receipts"
    assert "2 receipts match" in blocker["message"]
    assert "by hand" in blocker["message"]
    assert blocker["params"] == {"count": "2", "receipts": "WH/IN/00007, WH/IN/00008"}


# ---------------------------------------------------------------------------- the push


def test_pushing_creates_a_draft_carrying_our_own_split(
    client: TestClient, db: Session, org: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    odoo = WritableOdoo()
    connect(client, odoo, monkeypatch)
    container_id = seed_container(client)

    res = client.post(f"/api/v1/containers/{container_id}/erp/landed-cost")
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["odoo_model"] == "stock.landed.cost"
    assert body["odoo_id"] == 2
    assert body["status"] == "draft"  # never validated by us

    (values,) = odoo.created
    assert values["target_model"] == "picking"
    assert values["picking_ids"] == [(6, 0, [PICKING_ID])]
    assert values["name"] == "FreightSight MSCU4821990"
    (line_command,) = values["cost_lines"]
    assert line_command[2]["price_unit"] == 2766.67

    # and the adjustment line carries our exact amount, not Odoo's guess
    assert odoo.written == [(3, {"additional_landed_cost": 2766.67})]


def test_pushing_the_same_costs_twice_returns_the_first_push(
    client: TestClient, db: Session, org: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Writing a second document into someone's books because a button was clicked twice is not a
    mistake we get to make."""
    odoo = WritableOdoo()
    connect(client, odoo, monkeypatch)
    container_id = seed_container(client)

    first = client.post(f"/api/v1/containers/{container_id}/erp/landed-cost").json()
    second = client.post(f"/api/v1/containers/{container_id}/erp/landed-cost").json()
    assert first["id"] == second["id"]
    assert len(odoo.created) == 1
    assert len(list(db.scalars(select(ErpPush)))) == 1

    body = preview(client, container_id)
    assert body["already_pushed_as"] == "FreightSight MSCU4821990"
    assert "already_pushed" in [b["code"] for b in body["blockers"]]


def test_a_blocked_container_is_never_written(
    client: TestClient, db: Session, org: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    odoo = WritableOdoo(valued=False)
    connect(client, odoo, monkeypatch)
    container_id = seed_container(client)

    res = client.post(f"/api/v1/containers/{container_id}/erp/landed-cost")
    assert res.status_code == 422
    assert res.json()["code"] == "ERP_PUSH_BLOCKED"
    assert odoo.created == []
    assert list(db.scalars(select(ErpPush))) == []


def test_an_odoo_error_comes_back_in_its_own_words(
    client: TestClient, org: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect(client, WritableOdoo(fail_create=True), monkeypatch)
    container_id = seed_container(client)

    res = client.post(f"/api/v1/containers/{container_id}/erp/landed-cost")
    assert res.status_code == 502
    assert "Please configure Stock Valuation Account" in res.json()["detail"]


def test_the_push_is_in_the_audit_log(
    client: TestClient, org: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect(client, WritableOdoo(), monkeypatch)
    container_id = seed_container(client)
    client.post(f"/api/v1/containers/{container_id}/erp/landed-cost")

    entry = client.get("/api/v1/audit-log", params={"action": "erp.landed_cost_pushed"}).json()["entries"][0]
    assert entry["after"]["odoo_id"] == 2
    assert entry["after"]["status"] == "draft"
    assert entry["entity_type"] == "container"


def test_pushes_are_invisible_to_another_organization(
    client: TestClient, db: Session, org: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect(client, WritableOdoo(), monkeypatch)
    container_id = seed_container(client)
    client.post(f"/api/v1/containers/{container_id}/erp/landed-cost")

    db.execute(text("SET ROLE freightsight_app"))
    try:
        set_current_org(db, org.id)
        assert len(list(db.scalars(select(ErpPush)))) == 1
        set_current_org(db, uuid.uuid4())
        assert list(db.scalars(select(ErpPush))) == []
    finally:
        db.execute(text("RESET ROLE"))
        set_current_org(db, org.id)
