"""Taking any file back: what it created goes, what stands on it holds it, and the same file loads again.

A person drops the wrong price list, the wrong orders, the wrong tracking sheet — or drops the right
file on the wrong step. Each has a way back: a file not imported yet is discarded or read as the kind
it is, and an imported one is taken back with exactly the rows it created. The tester's kit is the
long case: its four files taken back one by one leave the organization as empty as it started."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from previews import commit_previewed
from sqlalchemy.orm import Session

from app.domain.models import ImportJob, Organization
from app.jobs import handlers

KIT = Path(__file__).resolve().parents[2] / "docs" / "demo" / "kit-testeur"
FILES = {
    "PRODUCTS": "1-tarif.csv",
    "PURCHASE_ORDERS": "2-commandes.csv",
    "CONTAINERS": "3-suivi-conteneurs.csv",
    "COSTS": "4-frais-trimestre.csv",
}
L1, H1 = "MSCU6702211", "MSCU6614208"
NOTHING = {
    "discarded": False,
    "costs_deleted": 0,
    "estimates_reopened": 0,
    "products_deleted": 0,
    "suppliers_deleted": 0,
    "purchase_orders_deleted": 0,
    "lines_deleted": 0,
    "containers_deleted": 0,
    "shipments_deleted": 0,
    "loads_deleted": 0,
}
TARIFF = "Référence;Désignation;Code SH;Taux de droits;Prix de vente HT;Devise de vente"


def text(*lines: str) -> bytes:
    return ("﻿" + "\n".join(lines) + "\n").encode()


def dropped(client: TestClient, kind: str, name: str | None = None, content: bytes | None = None) -> Any:
    name = name or FILES[kind]
    res = client.post(
        "/api/v1/imports",
        data={"kind": kind},
        files={"file": (name, content or (KIT / name).read_bytes(), "text/csv")},
    )
    assert res.status_code == 201, res.text
    return res.json()


def imported(client: TestClient, kind: str, name: str | None = None, content: bytes | None = None) -> Any:
    job = dropped(client, kind, name, content)
    previewed = client.post(f"/api/v1/imports/{job['id']}/validate", json={"mapping": job["mapping"]})
    assert previewed.status_code == 200, previewed.text
    committed = commit_previewed(client, job["id"])
    assert committed.status_code == 200, committed.text
    return committed.json()


def taken_back(client: TestClient, job: dict[str, Any]) -> dict[str, Any]:
    res = client.delete(f"/api/v1/imports/{job['id']}")
    assert res.status_code == 200, res.text
    deleted: dict[str, Any] = res.json()
    return deleted


def refused(client: TestClient, job: dict[str, Any]) -> dict[str, Any]:
    res = client.delete(f"/api/v1/imports/{job['id']}")
    assert res.status_code == 422, res.text
    problem: dict[str, Any] = res.json()
    return problem


def numbers(client: TestClient) -> dict[str, dict[str, Any]]:
    return {c["container_number"]: c for c in client.get("/api/v1/containers").json()}


def test_a_file_never_imported_is_discarded_and_leaves_no_trace(client: TestClient) -> None:
    job = dropped(client, "PRODUCTS")
    assert (job["status"], job["can_undo"]) == ("PARSED", True)
    assert taken_back(client, job) == NOTHING | {"discarded": True}
    assert client.get(f"/api/v1/imports/{job['id']}").status_code == 404
    assert client.get("/api/v1/imports").json() == []
    assert client.get("/api/v1/audit-log", params={"entity_id": job["id"]}).json()["entries"] == []


def test_a_price_list_taken_back_takes_the_articles_it_created_and_no_other(client: TestClient) -> None:
    imported(client, "PRODUCTS", "tarif.csv", text(TARIFF, "TYRE;Pneu;40111000;4,5;60,00;EUR"))
    second = imported(
        client,
        "PRODUCTS",
        "tarif-2.csv",
        text(TARIFF, "TYRE;Pneu;40111000;4,5;62,00;EUR", "PUMP;Pompe;84138100;1,7;19,00;EUR"),
    )
    assert (second["report"]["products_created"], second["report"]["products_updated"]) == (1, 1)
    assert second["can_undo"] is True

    assert taken_back(client, second) == NOTHING | {"products_deleted": 1}
    kept = {p["sku"]: p for p in client.get("/api/v1/products").json()["products"]}
    # The article that was there before keeps what the file changed on it: only what a file created
    # goes with it.
    assert {sku: p["sale_price"] for sku, p in kept.items()} == {"TYRE": "62.0000"}

    after = client.get(f"/api/v1/imports/{second['id']}").json()
    assert (after["can_undo"], after["undone_at"] is not None) == (False, True)
    again = client.delete(f"/api/v1/imports/{second['id']}")
    assert (again.status_code, again.json()["code"]) == (409, "IMPORT_ALREADY_UNDONE")
    page = client.get("/api/v1/audit-log", params={"entity_id": second["id"]}).json()
    (undone,) = [e["after"] for e in page["entries"] if e["action"] == "import.undone"]
    assert undone == {"kind": "PRODUCTS", "file_name": "tarif-2.csv", "products_deleted": 1}


def test_the_kit_taken_back_file_by_file_leaves_nothing_and_loads_again(client: TestClient) -> None:
    def load_all() -> dict[str, Any]:
        return {kind: imported(client, kind) for kind in FILES}

    jobs = load_all()
    first = {kind: job["report"] for kind, job in jobs.items()}
    assert (first["CONTAINERS"]["containers_created"], first["COSTS"]["costs_created"]) == (10, 42)
    assert len(client.get("/api/v1/alerts").json()) == 1  # L1, still at the terminal

    # Nothing is pulled from under what stands on it: the later files are named, latest first.
    held = refused(client, jobs["PURCHASE_ORDERS"])
    assert (held["code"], held["files"]) == ("IMPORT_RELIED_ON", [FILES["COSTS"], FILES["CONTAINERS"]])
    held = refused(client, jobs["CONTAINERS"])
    assert (held["code"], held["files"]) == ("IMPORT_RELIED_ON", [FILES["COSTS"]])
    assert len(numbers(client)) == 10

    assert taken_back(client, jobs["COSTS"]) == NOTHING | {"costs_deleted": 42}
    assert taken_back(client, jobs["CONTAINERS"]) == NOTHING | {
        "containers_deleted": 10,
        "shipments_deleted": 10,
        "loads_deleted": 14,
    }
    assert numbers(client) == {}
    assert client.get("/api/v1/alerts").json() == []
    assert taken_back(client, jobs["PURCHASE_ORDERS"]) == NOTHING | {
        "purchase_orders_deleted": 11,
        "lines_deleted": 14,
        "suppliers_deleted": 3,
    }
    assert client.get("/api/v1/purchase-orders").json() == []
    assert client.get("/api/v1/suppliers").json() == []
    assert taken_back(client, jobs["PRODUCTS"]) == NOTHING | {"products_deleted": 5}
    assert client.get("/api/v1/products").json()["products"] == []

    # The same four files say the same thing to an organization that is empty again.
    again = {kind: job["report"] for kind, job in load_all().items()}
    for kind in FILES:
        assert again[kind] == first[kind], kind


def test_a_price_list_goes_whatever_was_ordered_since(client: TestClient) -> None:
    # Order lines keep what they copied from the catalogue: taking it back moves no landed cost.
    tariff = imported(client, "PRODUCTS")
    imported(client, "PURCHASE_ORDERS")
    assert taken_back(client, tariff) == NOTHING | {"products_deleted": 5}
    orders = client.get("/api/v1/purchase-orders").json()
    assert len(orders) == 11


def test_a_cost_a_person_entered_holds_the_tracking_sheet(client: TestClient) -> None:
    imported(client, "PURCHASE_ORDERS")
    tracking = imported(client, "CONTAINERS")
    box = numbers(client)[L1]
    cost = client.post(
        "/api/v1/costs",
        json={
            "scope": "CONTAINER",
            "target_id": box["id"],
            "cost_type": "THC",
            "amount": "285.00",
            "currency": "EUR",
            "cost_date": "2026-11-20",
            "invoice_number": "MHL-26-0571",
        },
    )
    assert cost.status_code == 201, cost.text

    held = refused(client, tracking)
    assert (held["code"], held["count"], held["containers"], held["invoices"]) == (
        "IMPORT_ROWS_CARRY_COSTS",
        1,
        [L1],
        ["MHL-26-0571"],
    )
    assert len(numbers(client)) == 10  # nothing went

    assert client.delete(f"/api/v1/costs/{cost.json()['id']}").status_code == 204
    assert taken_back(client, tracking)["containers_deleted"] == 10


def test_orders_loaded_by_hand_hold_their_file(client: TestClient) -> None:
    orders = imported(client, "PURCHASE_ORDERS")
    box = client.post("/api/v1/containers", json={"container_number": "MSCU4821990"}).json()
    order = client.get("/api/v1/purchase-orders").json()[0]
    line = client.get(f"/api/v1/purchase-orders/{order['id']}").json()["lines"][0]
    loaded = client.put(
        f"/api/v1/containers/{box['id']}/loads",
        json=[{"po_line_id": line["id"], "quantity": line["quantity"]}],
    )
    assert loaded.status_code == 200, loaded.text

    held = refused(client, orders)
    assert (held["code"], held["count"], held["containers"]) == ("IMPORT_ROWS_LOADED", 1, ["MSCU4821990"])

    assert client.put(f"/api/v1/containers/{box['id']}/loads", json=[]).status_code == 200
    assert taken_back(client, orders)["purchase_orders_deleted"] == 11
    assert [c["container_number"] for c in client.get("/api/v1/containers").json()] == ["MSCU4821990"]


def test_a_closed_month_holds_the_tracking_sheet(client: TestClient) -> None:
    imported(client, "PURCHASE_ORDERS")
    tracking = imported(client, "CONTAINERS")
    assert client.post("/api/v1/periods/2026-07/close").status_code == 201

    held = refused(client, tracking)
    assert (held["code"], held["months"]) == ("IMPORT_PERIOD_CLOSED", ["2026-07"])
    assert len(numbers(client)) == 10


def test_a_file_committed_before_rows_were_kept_cannot_be_taken_back(client: TestClient, db: Session) -> None:
    job = imported(client, "PRODUCTS")
    stored = db.get(ImportJob, uuid.UUID(job["id"]))
    assert stored is not None and list(stored.created or {}) == ["products"]
    stored.created = None  # as every file committed before migration 0035
    db.commit()

    assert client.get(f"/api/v1/imports/{job['id']}").json()["can_undo"] is False
    assert refused(client, job)["code"] == "IMPORT_NOT_UNDOABLE"
    assert len(client.get("/api/v1/products").json()["products"]) == 5


@pytest.fixture
def org(client: TestClient, db: Session, org_id: uuid.UUID) -> Organization:
    assert client.get("/api/v1/organization").status_code == 200
    organization = db.get(Organization, org_id)
    assert organization is not None
    return organization


def test_an_invoice_being_reviewed_lets_go_of_a_container_taken_back(
    client: TestClient, db: Session, org: Organization
) -> None:
    imported(client, "PRODUCTS")
    imported(client, "PURCHASE_ORDERS")
    tracking = imported(client, "CONTAINERS")
    name = f"5-facture-transitaire-{L1}.pdf"
    invoice_id = client.post(
        "/api/v1/invoices", files={"file": (name, (KIT / name).read_bytes(), "application/pdf")}
    ).json()["id"]
    assert handlers.extract_invoice(db, org.id, uuid.UUID(invoice_id)) == "NEEDS_REVIEW"
    first = numbers(client)[L1]["id"]
    lines = client.get(f"/api/v1/invoices/{invoice_id}").json()["lines"]
    assert {line["target_id"] for line in lines} == {first}

    # Confirming these lines would have put five costs on a container that is no longer there.
    assert taken_back(client, tracking)["containers_deleted"] == 10
    lines = client.get(f"/api/v1/invoices/{invoice_id}").json()["lines"]
    assert {(line["scope"], line["target_id"]) for line in lines} == {(None, None)}
    assert all(f"@unknown_container|{L1}" in line["notes"] for line in lines)

    # The sheet read again finds them, as it finds any invoice that named a box nobody knew.
    again = imported(client, "CONTAINERS")
    assert again["report"]["invoices_matched"] == 1
    second = numbers(client)[L1]["id"]
    assert second != first
    lines = client.get(f"/api/v1/invoices/{invoice_id}").json()["lines"]
    assert {line["target_id"] for line in lines} == {second}


@pytest.mark.parametrize("file_kind", list(FILES))
@pytest.mark.parametrize("dropped_as", list(FILES))
def test_a_file_dropped_on_the_wrong_step_says_which_one_it_is(
    client: TestClient, file_kind: str, dropped_as: str
) -> None:
    job = dropped(client, dropped_as, FILES[file_kind])
    assert job["reads_like"] == (None if dropped_as == file_kind else file_kind)


def test_a_price_list_dropped_as_orders_is_read_as_a_price_list(client: TestClient) -> None:
    job = dropped(client, "PURCHASE_ORDERS", FILES["PRODUCTS"])
    assert job["reads_like"] == "PRODUCTS"
    # Previewed as orders it has nothing to say; that preview does not survive the change of kind.
    assert client.post(f"/api/v1/imports/{job['id']}/validate", json={"mapping": {}}).status_code == 422

    read = client.post(f"/api/v1/imports/{job['id']}/kind", json={"kind": "PRODUCTS"})
    assert read.status_code == 200, read.text
    again = read.json()
    assert (again["kind"], again["status"], again["reads_like"], again["error_count"]) == (
        "PRODUCTS",
        "PARSED",
        None,
        0,
    )
    assert again["mapping"]["sku"] == "Référence" and len(again["mapping"]) == 8
    previewed = client.post(f"/api/v1/imports/{job['id']}/validate", json={"mapping": again["mapping"]})
    assert previewed.status_code == 200, previewed.text
    assert commit_previewed(client, job["id"]).json()["report"]["products_created"] == 5


def test_a_file_already_imported_keeps_its_kind_and_a_ledger_is_not_read_twice(client: TestClient) -> None:
    done = imported(client, "PRODUCTS")
    changed = client.post(f"/api/v1/imports/{done['id']}/kind", json={"kind": "PURCHASE_ORDERS"})
    assert (changed.status_code, changed.json()["code"]) == (409, "IMPORT_ALREADY_DONE")

    imported(client, "PURCHASE_ORDERS")
    imported(client, "CONTAINERS")
    imported(client, "COSTS")
    stray = dropped(client, "CONTAINERS", FILES["COSTS"])
    assert stray["reads_like"] == "COSTS"
    twice = client.post(f"/api/v1/imports/{stray['id']}/kind", json={"kind": "COSTS"})
    assert (twice.status_code, twice.json()["code"]) == (409, "FILE_ALREADY_IMPORTED")
