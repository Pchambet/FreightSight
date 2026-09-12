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
from sqlalchemy import delete, select, text
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
    """An Odoo that answers the write-back calls, keeping the documents it is told to create.

    The shapes are the captured ones; what the fake adds is memory, because the question "did a
    second click write a second document into the customer's books?" cannot be asked of a fake that
    replays the same answer whatever it is sent. Ids start where the capture's do, so a first push
    still lands on landed cost 2, cost line 2 and adjustment 3.
    """

    def __init__(self, *, valued: bool = True, receipts: int = 1, fail_create: bool = False) -> None:
        self.valued = valued
        self.receipts = receipts
        self.fail_create = fail_create
        self.created: list[dict[str, Any]] = []
        self.written: list[tuple[int, dict[str, Any]]] = []
        self.documents: dict[int, dict[str, Any]] = {}
        self._next_document = 2
        self._next_cost_line = 2
        self._next_adjustment = 3

    def proxy(self, url: str) -> Any:
        return _Common() if url.endswith("/common") else _Models(self)

    def create_document(self, values: dict[str, Any]) -> int:
        """Store a landed cost the way Odoo would, with its own ids for the lines."""
        document_id = self._next_document
        self._next_document += 1
        cost_lines = []
        for command in values.get("cost_lines") or []:
            line_id = self._next_cost_line
            self._next_cost_line += 1
            cost_lines.append({"id": line_id, **command[2]})
        pickings = [pid for command in values.get("picking_ids") or [] for pid in command[2]]
        self.documents[document_id] = {
            "id": document_id,
            "name": values.get("name") or f"LC/{document_id:05d}",
            "state": "draft",
            "description": values.get("description"),
            "picking_ids": pickings,
            "amount_total": round(sum(line["price_unit"] for line in cost_lines), 2),
            "cost_line_rows": cost_lines,
            "cost_lines": [line["id"] for line in cost_lines],
            "adjustments": [],
        }
        return document_id

    def compute(self, document_id: int) -> None:
        """What `compute_landed_cost` does: one adjustment line per cost line and per move, with
        Odoo's own split — which our code then overwrites."""
        document = self.documents[document_id]
        document["adjustments"] = []
        for line in document["cost_line_rows"]:
            for move in FIXTURE["moves"]:
                adjustment_id = self._next_adjustment
                self._next_adjustment += 1
                document["adjustments"].append(
                    {
                        "id": adjustment_id,
                        "move_id": [move["id"], move["product_id"][1]],
                        "cost_line_id": [line["id"], line["name"]],
                        "additional_landed_cost": line["price_unit"],  # Odoo's guess, not ours
                    }
                )
        document["valuation_adjustment_lines"] = [a["id"] for a in document["adjustments"]]

    def matching(self, domain: list[Any]) -> list[dict[str, Any]]:
        """The three operators the adapter actually sends, and no more."""
        out = []
        for document in self.documents.values():
            keep = True
            for field_name, operator, value in domain:
                actual = document.get(field_name)
                if operator == "=":
                    keep = keep and actual == value
                elif operator == "in":
                    keep = keep and bool(set(actual or []) & set(value))
                elif operator == "like":
                    keep = keep and value in (actual or "")
                else:  # pragma: no cover - the adapter sends nothing else
                    raise AssertionError(f"unsupported operator {operator}")
            if keep:
                out.append(document)
        return sorted(out, key=lambda d: d["id"])


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
                return self.odoo.create_document(args[0])
            case ("stock.landed.cost", "search_read"):
                fields = kwargs.get("fields") or []
                found = self.odoo.matching(args[0])[: kwargs.get("limit") or len(self.odoo.documents)]
                return [{"id": d["id"], **{f: d.get(f) for f in fields}} for d in found]
            case ("stock.landed.cost", "compute_landed_cost"):
                self.odoo.compute(args[0][0])
                return True
            case ("stock.landed.cost", "read"):
                document = self.odoo.documents[args[0][0]]
                return [{f: document.get(f) for f in ["id", *(kwargs.get("fields") or [])]}]
            case ("stock.valuation.adjustment.lines", "search_read"):
                document_id = args[0][0][2]
                return list(self.odoo.documents[document_id]["adjustments"])
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


def seed_container(client: TestClient, *, invoiced: bool = True, sku: str | None = SKU) -> str:
    """One container of the SKU Odoo received, with an invoiced ocean freight on it."""
    line: dict[str, Any] = {"line_no": 1, "quantity": "100", "unit_price": "10.00"}
    if sku is not None:
        line["sku"] = sku
    po = client.post(
        "/api/v1/purchase-orders",
        json={"po_number": PO_NUMBER, "currency": "EUR", "lines": [line]},
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


def test_a_push_interrupted_after_the_erp_write_is_resumed_not_repeated(
    client: TestClient, db: Session, org: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Creating the draft and recording it here are two writes to two systems.

    If the second one is lost — the connection drops, the transaction rolls back — the draft exists
    in the customer's books with nothing here pointing at it, and the obvious next move (click the
    button again) would put a second one in their accounts. The marker in the document is how the
    retry recognises its own work.
    """
    odoo = WritableOdoo()
    connect(client, odoo, monkeypatch)
    container_id = seed_container(client)

    first = client.post(f"/api/v1/containers/{container_id}/erp/landed-cost")
    assert first.status_code == 201, first.text

    # the crash: Odoo kept the draft, our commit never landed
    db.execute(delete(ErpPush))
    db.commit()
    assert odoo.documents[2]["state"] == "draft"

    second = client.post(f"/api/v1/containers/{container_id}/erp/landed-cost")
    assert second.status_code == 201, second.text
    assert second.json()["odoo_id"] == first.json()["odoo_id"]

    assert len(odoo.created) == 1  # one document in their books, not two
    assert len(odoo.documents) == 1
    (record,) = list(db.scalars(select(ErpPush)))
    assert record.odoo_id == 2
    assert record.response["freightsight_adopted"] is True
    # and it carries our amounts, written again over whatever the interrupted attempt left.
    # The adjustment line has a new id: recomputing replaces those lines, here as in Odoo.
    (adjustment,) = odoo.documents[2]["adjustments"]
    assert odoo.written[-1] == (adjustment["id"], {"additional_landed_cost": 2766.67})


def test_a_second_invoice_is_refused_rather_than_charged_twice(
    client: TestClient, db: Session, org: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A landed cost adds to the stock valuation; it does not replace the last one.

    So when a customs invoice lands after the freight has been pushed, the plan — which always
    recomputes over every actual cost on the container — would carry the freight a second time and
    charge the goods twice. Refused, and said out loud, until we decide how to push only the
    difference. See docs/odoo-questions.md section 15.
    """
    odoo = WritableOdoo()
    connect(client, odoo, monkeypatch)
    container_id = seed_container(client)
    first = client.post(f"/api/v1/containers/{container_id}/erp/landed-cost")
    assert first.status_code == 201, first.text

    late = client.post(
        "/api/v1/costs",
        json={
            "scope": "CONTAINER",
            "target_id": container_id,
            "cost_type": "CUSTOMS_DUTY",
            "amount": "275.00",
            "currency": "EUR",
            "cost_date": "2026-03-20",
            "invoice_number": "FA-2026-1104",
        },
    )
    assert late.status_code == 201, late.text

    body = preview(client, container_id)
    assert body["pushable"] is False
    blocker = next(b for b in body["blockers"] if b["code"] == "partially_pushed")
    assert blocker["params"] == {"existing": "FreightSight MSCU4821990", "count": "1"}
    assert "charge the goods twice" in blocker["message"]

    res = client.post(f"/api/v1/containers/{container_id}/erp/landed-cost")
    assert res.status_code == 422
    assert len(odoo.documents) == 1  # their books still hold one document, not two


def test_the_marker_is_the_set_of_costs_whatever_order_it_arrives_in() -> None:
    from app.domain.erp.landed_cost import marker_for

    one, two = uuid.uuid4(), uuid.uuid4()
    assert marker_for([one, two]) == marker_for([two, one])
    assert marker_for([one, two]) == marker_for([str(two), str(one)])
    assert marker_for([one]) != marker_for([one, two])
    assert len(marker_for([one])) == 16


def test_a_draft_edited_by_hand_is_refused_rather_than_overwritten(
    client: TestClient, db: Session, org: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Our marker on a document whose lines no longer match ours means someone changed it. Writing
    our numbers back over their edit would be us deciding what they meant."""
    odoo = WritableOdoo()
    connect(client, odoo, monkeypatch)
    container_id = seed_container(client)
    client.post(f"/api/v1/containers/{container_id}/erp/landed-cost")
    db.execute(delete(ErpPush))
    db.commit()

    document = odoo.documents[2]
    document["cost_lines"] = [*document["cost_lines"], 99]  # a line added in Odoo

    res = client.post(f"/api/v1/containers/{container_id}/erp/landed-cost")
    assert res.status_code == 502
    assert res.json()["code"] == "ERP_DRAFT_EDITED"
    assert len(odoo.created) == 1  # and nothing new was written


def test_a_validated_landed_cost_is_never_adopted(
    client: TestClient, db: Session, org: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Once validated, the document is posted in the accounts. It is not ours to write into again,
    so the retry makes a new draft rather than touching it."""
    odoo = WritableOdoo()
    connect(client, odoo, monkeypatch)
    container_id = seed_container(client)
    client.post(f"/api/v1/containers/{container_id}/erp/landed-cost")
    db.execute(delete(ErpPush))
    db.commit()
    odoo.documents[2]["state"] = "done"

    res = client.post(f"/api/v1/containers/{container_id}/erp/landed-cost")
    assert res.status_code == 201
    assert res.json()["odoo_id"] != 2
    assert odoo.documents[2]["state"] == "done"  # untouched


def test_a_line_the_receipt_does_not_have_stops_the_push(
    client: TestClient, db: Session, org: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Costs are pushed per line. A line we cannot place on the receipt would either be dropped
    silently or land on the wrong product, so it is refused with the line named."""
    odoo = WritableOdoo()
    connect(client, odoo, monkeypatch)
    container_id = seed_container(client, sku="NOT-IN-ODOO")

    body = preview(client, container_id)
    assert body["pushable"] is False
    blocker = next(b for b in body["blockers"] if b["code"] == "unmatched_line")
    assert blocker["params"] == {
        "po_number": PO_NUMBER,
        "line_no": "1",
        "sku": "NOT-IN-ODOO",
        "receipt": "WH/IN/00007",
    }

    res = client.post(f"/api/v1/containers/{container_id}/erp/landed-cost")
    assert res.status_code == 422
    assert res.json()["code"] == "ERP_PUSH_BLOCKED"
    assert odoo.created == []
    assert list(db.scalars(select(ErpPush))) == []


def test_a_line_with_no_sku_at_all_says_so_without_inventing_one(
    client: TestClient, org: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The SKU is the only identifier both systems share. Without one there is nothing to match on,
    and `params.sku` is empty rather than our English for it."""
    connect(client, WritableOdoo(), monkeypatch)
    container_id = seed_container(client, sku=None)

    body = preview(client, container_id)
    blocker = next(b for b in body["blockers"] if b["code"] == "unmatched_line")
    assert blocker["params"]["sku"] == ""
    assert "no SKU" in blocker["message"]


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
