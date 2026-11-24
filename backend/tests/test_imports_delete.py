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

    # Nothing is pulled from under what stands on it: the file that does is named, one step at a time.
    held = refused(client, jobs["PURCHASE_ORDERS"])
    assert (held["code"], held["files"]) == ("IMPORT_RELIED_ON", [FILES["CONTAINERS"]])
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


# ---------------------------------------------------------------------------- what else stands on a file


def reading(client: TestClient, db: Session, org: Organization, name: str) -> str:
    invoice_id: str = client.post(
        "/api/v1/invoices", files={"file": (name, (KIT / name).read_bytes(), "application/pdf")}
    ).json()["id"]
    assert handlers.extract_invoice(db, org.id, uuid.UUID(invoice_id)) == "NEEDS_REVIEW"
    return invoice_id


def test_an_invoice_rejected_lets_go_too_and_reopened_puts_no_cost_on_a_box_that_is_gone(
    client: TestClient, db: Session, org: Organization
) -> None:
    imported(client, "PRODUCTS")
    imported(client, "PURCHASE_ORDERS")
    tracking = imported(client, "CONTAINERS")
    invoice_id = reading(client, db, org, f"5-facture-transitaire-{L1}.pdf")
    assert client.post(f"/api/v1/invoices/{invoice_id}/reject").status_code == 200

    # A rejected invoice is reopened as it stands: its lines must not still point at the old box.
    assert taken_back(client, tracking)["containers_deleted"] == 10
    lines = client.get(f"/api/v1/invoices/{invoice_id}").json()["lines"]
    assert {(line["scope"], line["target_id"]) for line in lines} == {(None, None)}
    imported(client, "CONTAINERS")
    assert client.get("/api/v1/costs", params={"target_id": numbers(client)[L1]["id"]}).json() == []


def test_an_invoice_is_not_confirmed_on_a_container_deleted_by_hand(
    client: TestClient, db: Session, org: Organization
) -> None:
    imported(client, "PRODUCTS")
    imported(client, "PURCHASE_ORDERS")
    imported(client, "CONTAINERS")
    invoice_id = reading(client, db, org, f"5-facture-transitaire-{L1}.pdf")
    for line in client.get(f"/api/v1/invoices/{invoice_id}").json()["lines"]:
        accepted = client.patch(f"/api/v1/invoices/{invoice_id}/lines/{line['id']}", json={"accepted": True})
        assert accepted.is_success
    box = numbers(client)[L1]["id"]
    assert client.delete(f"/api/v1/containers/{box}").status_code == 204

    confirmed = client.post(f"/api/v1/invoices/{invoice_id}/confirm")
    assert (confirmed.status_code, confirmed.json()["code"]) == (422, "UNKNOWN_TARGET")
    assert client.get("/api/v1/costs", params={"target_id": box}).json() == []


def test_a_cost_on_a_bill_the_file_joined_holds_it_even_when_it_could_not_be_spread(
    client: TestClient,
) -> None:
    # No price list: the order lines have no weight, so a freight split by weight lands on nothing
    # yet. Taking the sheet back would change what it will land on all the same.
    imported(client, "PURCHASE_ORDERS")
    bill = client.post("/api/v1/shipments", json={"reference": "MEDUNB2601184"})  # H1's bill, by hand
    assert bill.status_code == 201, bill.text
    tracking = imported(client, "CONTAINERS")
    assert tracking["report"]["shipments_created"] == 9  # H1 joined the bill that was there
    cost = client.post(
        "/api/v1/costs",
        json={
            "scope": "SHIPMENT",
            "target_id": bill.json()["id"],
            "cost_type": "OCEAN_FREIGHT",
            "amount": "1000.00",
            "currency": "EUR",
            "cost_date": "2026-07-10",
            "allocation_method": "BY_WEIGHT",
        },
    )
    assert cost.status_code == 201, cost.text
    assert numbers(client)[H1]["allocated_base"] == "0.00"  # held: nothing to weigh

    held = refused(client, tracking)
    assert (held["code"], held["count"]) == ("IMPORT_ROWS_CARRY_COSTS", 1)
    assert len(numbers(client)) == 10


def test_a_line_a_person_added_stays_with_its_order(client: TestClient) -> None:
    orders = imported(client, "PURCHASE_ORDERS")
    order = next(o for o in client.get("/api/v1/purchase-orders").json() if o["po_number"] == "PO-2026-041")
    added = client.patch(
        f"/api/v1/purchase-orders/{order['id']}",
        json={"lines": [{"line_no": 9, "sku": "HAND", "quantity": "3", "unit_price": "10.00"}]},
    )
    assert added.status_code == 200, added.text

    # Only what the file created is the file's to delete: the order keeps the line it did not write.
    assert taken_back(client, orders) == NOTHING | {
        "purchase_orders_deleted": 10,
        "lines_deleted": 14,
        "suppliers_deleted": 2,
    }
    (kept,) = client.get("/api/v1/purchase-orders").json()
    lines = client.get(f"/api/v1/purchase-orders/{kept['id']}").json()["lines"]
    assert (kept["po_number"], [line["sku"] for line in lines]) == ("PO-2026-041", ["HAND"])


def test_the_same_orders_said_again_hold_the_file_that_created_them(client: TestClient, db: Session) -> None:
    first = imported(client, "PURCHASE_ORDERS")
    again = imported(
        client, "PURCHASE_ORDERS", "2-commandes (2).csv", (KIT / FILES["PURCHASE_ORDERS"]).read_bytes()
    )
    assert again["report"]["purchase_orders_created"] == 0
    stored = db.get(ImportJob, uuid.UUID(first["id"]))
    assert stored is not None and stored.matched == {}  # what a file created is not what it matched

    held = refused(client, first)
    assert (held["code"], held["files"]) == ("IMPORT_RELIED_ON", ["2-commandes (2).csv"])
    assert len(client.get("/api/v1/purchase-orders").json()) == 11
    assert taken_back(client, again) == NOTHING  # it had created nothing
    assert taken_back(client, first)["purchase_orders_deleted"] == 11


def test_a_price_list_repriced_since_is_held_by_the_later_one(client: TestClient) -> None:
    first = imported(client, "PRODUCTS", "tarif.csv", text(TARIFF, "TYRE;Pneu;40111000;4,5;60,00;EUR"))
    second = imported(client, "PRODUCTS", "tarif-2.csv", text(TARIFF, "TYRE;Pneu;40111000;4,5;62,00;EUR"))
    assert second["report"]["products_updated"] == 1

    held = refused(client, first)
    assert (held["code"], held["files"]) == ("IMPORT_RELIED_ON", ["tarif-2.csv"])
    assert taken_back(client, second) == NOTHING
    assert taken_back(client, first) == NOTHING | {"products_deleted": 1}


def test_a_box_an_orders_file_created_and_a_sheet_dated_is_held_by_the_sheet(client: TestClient) -> None:
    orders = imported(
        client,
        "PURCHASE_ORDERS",
        "commandes.csv",
        text("N° commande;Référence;Quantité;Prix unitaire;N° conteneur", f"PO-A;TYRE;100;10,00;{H1}"),
    )
    assert orders["report"]["containers_created"] == 1
    sheet = imported(
        client,
        "CONTAINERS",
        "suivi.csv",
        text("N° conteneur;N° B/L;Arrivée réelle", f"{H1};MEDU1234567;07/07/2026"),
    )
    assert (sheet["report"]["containers_created"], sheet["report"]["containers_updated"]) == (0, 1)

    held = refused(client, orders)
    assert (held["code"], held["files"]) == ("IMPORT_RELIED_ON", ["suivi.csv"])
    # What the sheet only changed keeps its value: the box stays dated, on the bill the sheet opened,
    # and a bill a box still travels on is not deleted.
    assert taken_back(client, sheet) == NOTHING
    assert taken_back(client, orders) == NOTHING | {
        "purchase_orders_deleted": 1,
        "lines_deleted": 1,
        "containers_deleted": 1,
        "loads_deleted": 1,
    }


def test_rows_an_erp_sync_keeps_in_step_are_no_longer_the_file_s(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = imported(client, "PURCHASE_ORDERS")
    synced = imported(
        client, "PURCHASE_ORDERS", "odoo-sync.csv", (KIT / FILES["PURCHASE_ORDERS"]).read_bytes()
    )
    from app.domain.imports import undo

    monkeypatch.setattr(undo, "synced_jobs", lambda t, ids: {uuid.UUID(synced["id"])} & set(ids))

    # Naming a file that cannot be taken back would be a dead end: the refusal says whose rows they are.
    held = refused(client, first)
    assert (held["code"], "files" in held) == ("IMPORT_HELD_BY_ERP_SYNC", False)
    assert refused(client, synced)["code"] == "IMPORT_NOT_UNDOABLE"
    assert len(client.get("/api/v1/purchase-orders").json()) == 11


def test_a_file_of_tens_of_thousands_of_rows_is_taken_back_in_one_statement(
    client: TestClient, db: Session
) -> None:
    job = imported(client, "PURCHASE_ORDERS")
    stored = db.get(ImportJob, uuid.UUID(job["id"]))
    assert stored is not None and stored.created is not None
    # More ids than a statement holds parameters (65 535), as a 70 000-line file would keep.
    stored.created = stored.created | {
        "po_lines": [*stored.created["po_lines"], *(str(uuid.uuid4()) for _ in range(70_000))]
    }
    db.commit()

    assert taken_back(client, job)["lines_deleted"] == 14


# ---------------------------------------------------------------------------- what a file reads like


def reads_like(client: TestClient, kind: str, *lines: str) -> Any:
    return dropped(client, kind, "export.csv", text(*lines))["reads_like"]


def test_an_orders_export_that_carries_tracking_columns_is_an_orders_file(client: TestClient) -> None:
    header = "N° commande;Référence;Quantité;Prix unitaire;N° conteneur;N° B/L;Port de chargement;ETD;ETA"
    row = "PO-A;TYRE;100;10,00;MSCU4821990;MEDU1234567;Ningbo;03/06/2026;07/07/2026"
    assert reads_like(client, "PURCHASE_ORDERS", header, row) is None


def test_a_preview_refused_with_no_mapping_says_nothing_about_the_file(client: TestClient) -> None:
    job = dropped(client, "PURCHASE_ORDERS")
    assert client.post(f"/api/v1/imports/{job['id']}/validate", json={"mapping": {}}).status_code == 422
    assert client.get(f"/api/v1/imports/{job['id']}").json()["reads_like"] is None


def test_a_price_list_without_prices_dropped_as_orders_is_still_a_price_list(client: TestClient) -> None:
    header = "Référence;Désignation;Code SH;Taux de droits;Poids unitaire (kg)"
    assert reads_like(client, "PURCHASE_ORDERS", header, "TYRE;Pneu;40111000;4,5;9,5") == "PRODUCTS"
    # One column in common is not a likeness: a ledger with a « Référence » column is no price list.
    ledger = "Date;Référence;Libellé;Débit"
    assert reads_like(client, "COSTS", ledger, "10/07/2026;F-1;Fret maritime;3 480,00") is None
