"""The Odoo connector, against fixtures taken from a real Odoo 17, and the sync that uses it."""

from __future__ import annotations

import base64
import json
import uuid
import xmlrpc.client
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.adapters.erp.odoo import OdooConnector
from app.core.crypto import CryptoError
from app.core.tenancy import set_current_org
from app.domain.erp.ports import ErpAuthError, ErpProtocolError, ErpUnavailable
from app.domain.erp.service import open_key, seal_key, to_csv
from app.domain.models import ErpConnection, ErpSyncRun, Organization

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "odoo" / "purchase_orders.json").read_text())
ERP_KEY = base64.b64encode(b"e" * 32).decode()


@pytest.fixture(autouse=True)
def erp_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    import os

    from app.core.settings import get_settings

    monkeypatch.setenv("ERP_ENCRYPTION_KEY", ERP_KEY)
    # Settings are read from the environment, and a test that never touches the database has not had
    # one set for it by the harness.
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


class FakeOdoo:
    """An Odoo that answers from the captured fixture, and only to the calls we actually make."""

    def __init__(self, *, password: str = "the-api-key", fail: str | None = None) -> None:
        self.password = password
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    def proxy(self, url: str) -> Any:
        return _Common(self) if url.endswith("/common") else _Models(self)


class _Common:
    def __init__(self, odoo: FakeOdoo) -> None:
        self.odoo = odoo

    def version(self) -> dict[str, str]:
        if self.odoo.fail == "unreachable":
            raise OSError("connection refused")
        return {"server_version": FIXTURE["version"]}

    def authenticate(self, db: str, login: str, password: str, _context: dict[str, Any]) -> Any:
        if self.odoo.fail == "unreachable":
            raise OSError("connection refused")
        if self.odoo.fail == "no-database":
            raise xmlrpc.client.Fault(3, "Traceback...\npsycopg2.OperationalError: database does not exist")
        return 2 if password == self.odoo.password else False


class _Models:
    def __init__(self, odoo: FakeOdoo) -> None:
        self.odoo = odoo

    def execute_kw(
        self, db: str, uid: int, password: str, model: str, method: str, args: list[Any], kwargs: Any
    ) -> Any:
        self.odoo.calls.append((model, method))
        if self.odoo.fail == "protocol":
            raise xmlrpc.client.Fault(1, "Traceback...\nValueError: Invalid field 'nope' on model")
        match (model, method):
            case ("res.users", "read"):
                return [{"id": 2, "name": "Mitchell Admin", "company_id": [1, "YourCompany"]}]
            case ("purchase.order", "search_read"):
                orders = FIXTURE["orders"]
                return orders[: kwargs["limit"]] if kwargs.get("limit") else orders
            case ("purchase.order.line", "search_read"):
                return FIXTURE["lines"]
            case ("product.product", "fields_get"):
                return {"default_code": {"type": "char"}, "weight": {"type": "float"}}
            case ("product.product", "read"):
                return FIXTURE["products"]
            case ("uom.uom", "read"):
                return FIXTURE["uoms"]
        raise AssertionError(f"unexpected call {model}.{method}")  # pragma: no cover


def connector(odoo: FakeOdoo, *, api_key: str = "the-api-key") -> OdooConnector:
    return OdooConnector("https://erp.example.test", "fstest", "admin", api_key, proxy_factory=odoo.proxy)


# ---------------------------------------------------------------------------- connecting


def test_a_successful_connection_reports_what_it_found() -> None:
    identity = connector(FakeOdoo()).test_connection()
    assert identity.server_version.startswith("17.0")
    assert identity.database == "fstest"
    assert identity.user_id == 2
    assert identity.company == "YourCompany"


def test_a_wrong_key_is_not_an_exception_in_odoo_but_is_one_here() -> None:
    """`authenticate` answers False; a caller that does not check gets None back much later."""
    with pytest.raises(ErpAuthError) as raised:
        connector(FakeOdoo(), api_key="wrong").test_connection()
    assert "refused the credentials" in raised.value.message
    assert "API keys" in raised.value.message  # where to find one, since that is the usual mistake


def test_a_missing_database_says_what_odoo_said() -> None:
    with pytest.raises(ErpAuthError) as raised:
        connector(FakeOdoo(fail="no-database")).test_connection()
    assert "database does not exist" in raised.value.message  # the last line, not the traceback


def test_an_unreachable_server_is_not_an_authentication_problem() -> None:
    with pytest.raises(ErpUnavailable):
        connector(FakeOdoo(fail="unreachable")).test_connection()


def test_a_renamed_field_surfaces_as_a_protocol_error() -> None:
    odoo = FakeOdoo()
    odoo.fail = "protocol"
    with pytest.raises(ErpProtocolError) as raised:
        connector(odoo).fetch_purchase_orders()
    assert "Invalid field" in raised.value.message


# ---------------------------------------------------------------------------- reading orders


def test_orders_and_lines_come_back_as_ours() -> None:
    orders = connector(FakeOdoo()).fetch_purchase_orders()
    assert [o.number for o in orders] == ["P00008", "P00009", "P00010"]
    order = next(o for o in orders if o.number == "P00009")
    assert order.supplier == "Gemini Furniture"
    assert order.currency == "USD"
    assert order.order_date is not None
    assert [line.sku for line in order.lines] == ["E-COM09", "E-COM06"]


def test_a_quantity_in_dozens_becomes_a_quantity_in_units() -> None:
    """The lesson from the real Odoo: `product_qty` is in the line's unit, the weight is per unit.

    Importing 20 where the customer means 240 would understate every weight-based allocation.
    """
    orders = connector(FakeOdoo()).fetch_purchase_orders()
    line = next(ln for o in orders for ln in o.lines if ln.sku == "E-COM09")
    assert line.uom == "Dozens"
    assert Decimal(line.quantity) == Decimal("240")
    assert Decimal(line.unit_price) == Decimal("41.6667")  # 500 per dozen
    # and the line total survives the conversion, to the cent it will be stored at
    assert abs(Decimal(line.quantity) * Decimal(line.unit_price) - Decimal("10000")) < Decimal("0.01")
    assert line.unit_weight_kg == "9.54"  # per unit, as the product carries it


def test_a_field_this_odoo_does_not_have_is_not_asked_for() -> None:
    """hs_code does not exist on product.product in Odoo 17 Community; asking would fail the sync."""
    odoo = FakeOdoo()
    orders = connector(odoo).fetch_purchase_orders()
    assert all(line.hs_code is None for order in orders for line in order.lines)
    assert ("product.product", "fields_get") in odoo.calls


# ---------------------------------------------------------------------------- the sealed credential


def test_the_api_key_is_sealed_and_comes_back() -> None:
    sealed = seal_key("the-api-key")
    assert b"the-api-key" not in sealed
    assert open_key(sealed) == "the-api-key"


def test_another_key_cannot_open_it(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.settings import get_settings

    sealed = seal_key("the-api-key")
    monkeypatch.setenv("ERP_ENCRYPTION_KEY", base64.b64encode(b"z" * 32).decode())
    get_settings.cache_clear()
    with pytest.raises(CryptoError):
        open_key(sealed)


def test_without_a_key_the_deployment_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.settings import get_settings

    monkeypatch.delenv("ERP_ENCRYPTION_KEY", raising=False)
    get_settings.cache_clear()
    with pytest.raises(CryptoError) as raised:
        seal_key("the-api-key")
    assert "ERP_ENCRYPTION_KEY" in str(raised.value)


# ---------------------------------------------------------------------------- the CSV bridge


def test_the_orders_are_written_in_our_own_import_columns() -> None:
    """The ERP goes through the same pipeline as a spreadsheet: one place for the rules."""
    orders = connector(FakeOdoo()).fetch_purchase_orders()
    content, lines = to_csv(orders)
    text_content = content.decode()
    assert lines == 5
    header = text_content.splitlines()[0]
    assert header.startswith("po_number,supplier_name,currency,order_date,line_no,sku")
    assert "P00009,Gemini Furniture,USD," in text_content
    assert "Large Desk (Dozens)" in text_content  # the unit stays legible to a human


# ---------------------------------------------------------------------------- through the API


def connect(client: TestClient, odoo: FakeOdoo, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    from app.adapters.erp import odoo as odoo_module

    monkeypatch.setattr(odoo_module, "_default_proxy", odoo.proxy)
    res = client.post(
        "/api/v1/erp/connection",
        json={
            "kind": "ODOO",
            "url": "https://erp.example.test/",
            "database": "fstest",
            "login": "admin",
            "api_key": "the-api-key",
        },
    )
    assert res.status_code == 201, res.text
    body: dict[str, Any] = res.json()
    return body


def test_connecting_tests_the_credentials_first(
    client: TestClient, db: Session, org: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = connect(client, FakeOdoo(), monkeypatch)
    assert body["server_version"].startswith("17.0")
    assert body["company"] == "YourCompany"
    assert "api_key" not in body  # never returned, in any form
    assert body["url"] == "https://erp.example.test"  # normalised

    stored = db.scalar(select(ErpConnection))
    assert stored is not None
    assert b"the-api-key" not in bytes(stored.api_key_sealed)


def test_bad_credentials_are_refused_before_anything_is_stored(
    client: TestClient, db: Session, org: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A saved connection that has never authenticated is a promise the next sync will break."""
    from app.adapters.erp import odoo as odoo_module

    monkeypatch.setattr(odoo_module, "_default_proxy", FakeOdoo(password="something-else").proxy)
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
    assert res.status_code == 422
    assert res.json()["code"] == "ERP_AUTH_FAILED"
    assert list(db.scalars(select(ErpConnection))) == []


def test_one_connection_per_organization(
    client: TestClient, org: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect(client, FakeOdoo(), monkeypatch)
    res = client.post(
        "/api/v1/erp/connection",
        json={
            "kind": "ODOO",
            "url": "https://erp.example.test",
            "database": "other",
            "login": "admin",
            "api_key": "k",
        },
    )
    assert res.status_code == 409
    assert res.json()["code"] == "ERP_ALREADY_CONNECTED"


def test_a_sync_imports_the_orders_and_is_idempotent(
    client: TestClient, db: Session, org: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect(client, FakeOdoo(), monkeypatch)

    first = client.post("/api/v1/erp/sync")
    assert first.status_code == 202, first.text
    assert first.json()["status"] == "SUCCEEDED"
    assert first.json()["purchase_orders"] == 3
    assert first.json()["lines"] == 5

    orders = client.get("/api/v1/purchase-orders").json()
    assert sorted(o["po_number"] for o in orders) == ["P00008", "P00009", "P00010"]

    # the same orders again: updated in place, never duplicated
    second = client.post("/api/v1/erp/sync")
    assert second.status_code == 202
    assert len(client.get("/api/v1/purchase-orders").json()) == 3

    runs = client.get("/api/v1/erp/sync-runs").json()
    assert len(runs) == 2
    assert all(run["status"] == "SUCCEEDED" for run in runs)


def test_a_failed_sync_leaves_a_run_that_says_why(
    client: TestClient, db: Session, org: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sync that fails silently is a customer who believes their orders are up to date."""
    connect(client, FakeOdoo(), monkeypatch)
    from app.adapters.erp import odoo as odoo_module

    monkeypatch.setattr(odoo_module, "_default_proxy", FakeOdoo(fail="protocol").proxy)
    res = client.post("/api/v1/erp/sync")
    assert res.status_code == 502

    runs = client.get("/api/v1/erp/sync-runs").json()
    assert runs[0]["status"] == "FAILED"
    assert "Invalid field" in runs[0]["error"]
    assert client.get("/api/v1/erp/connection").json()["last_error"]


def test_forgetting_the_erp_keeps_the_orders(
    client: TestClient, org: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect(client, FakeOdoo(), monkeypatch)
    client.post("/api/v1/erp/sync")
    assert client.delete("/api/v1/erp/connection").status_code == 204
    assert client.get("/api/v1/erp/connection").status_code == 404
    assert len(client.get("/api/v1/purchase-orders").json()) == 3  # they are ours now


def test_erp_rows_are_invisible_to_another_organization(
    client: TestClient, db: Session, org: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect(client, FakeOdoo(), monkeypatch)
    client.post("/api/v1/erp/sync")
    db.execute(text("SET ROLE freightsight_app"))
    try:
        set_current_org(db, org.id)
        assert len(list(db.scalars(select(ErpConnection)))) == 1
        assert len(list(db.scalars(select(ErpSyncRun)))) == 1
        set_current_org(db, uuid.uuid4())
        assert list(db.scalars(select(ErpConnection))) == []
        assert list(db.scalars(select(ErpSyncRun))) == []
    finally:
        db.execute(text("RESET ROLE"))
        set_current_org(db, org.id)
