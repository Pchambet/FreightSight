"""Reading a costs ledger — the money half of a prospect's quarter. Every rule in both directions: what
is read and on which target, what is refused and why, what is set aside and counted, and that the
same invoice line never lands twice, whatever door it came in by or how often the file is dropped."""

from __future__ import annotations

import time
import uuid
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from invoice_fixtures import FRENCH_ONE_CONTAINER
from pdfs import make_pdf
from sqlalchemy.orm import Session

from app.domain.boxes import check_digit
from app.domain.models import Organization
from app.jobs import handlers

HEADER = (
    "Date du coût;Prestataire;N° facture;Libellé;Type de coût;Montant HT;Devise;"
    "N° conteneur;N° B/L;N° commande"
)
THC_F1 = "12/03/2026;TRANSITEX;F-1;THC;;285,00;EUR;MSCU4821994;;"
FREIGHT_F1 = "12/03/2026;TRANSITEX;F-1;Fret maritime;;3 000,00;EUR;MSCU4821994;;"
MARCH = {"period_from": "2026-03-01", "period_to": "2026-03-31"}


@pytest.fixture
def org(client: TestClient, db: Session, org_id: uuid.UUID) -> Organization:
    assert client.get("/api/v1/organization").status_code == 200
    organization = db.get(Organization, org_id)
    assert organization is not None
    return organization


@pytest.fixture
def world(client: TestClient) -> dict[str, str]:
    """Two boxes on bill BL-A, a third alone on bill BL-C, all discharged in March, one order on the
    first: what a ledger's lines land on."""
    po = client.post(
        "/api/v1/purchase-orders",
        json={"po_number": "PO-1", "currency": "EUR", "lines": [
            {"line_no": 1, "sku": "TYRE", "quantity": "100", "unit_price": "10", "duty_rate": "0.10"},
            {"line_no": 2, "sku": "JACK", "quantity": "100", "unit_price": "10", "duty_rate": "0"}]},
    ).json()  # fmt: skip
    ids: dict[str, str] = {"PO-1": po["id"]}
    for reference in ("BL-A", "BL-C"):
        ids[reference] = client.post("/api/v1/shipments", json={"reference": reference}).json()["id"]
    for number, bill in (("MSCU4821994", "BL-A"), ("TGHU7245086", "BL-A"), ("CSQU3054383", "BL-C")):
        box = client.post("/api/v1/containers", json={"container_number": number, "iso_type": "42G1"}).json()
        patch = {"shipment_id": ids[bill], "discharged_at": "2026-03-10T12:00:00Z"}
        assert client.patch(f"/api/v1/containers/{box['id']}", json=patch).is_success
        ids[number] = box["id"]
    loads = [{"po_line_id": line["id"], "quantity": "100"} for line in po["lines"]]
    assert client.put(f"/api/v1/containers/{ids['MSCU4821994']}/loads", json=loads).status_code == 200
    return ids


def ledger(*rows: str, header: str = HEADER) -> bytes:
    return ("﻿" + "\n".join([header, *rows]) + "\n").encode()


def upload(client: TestClient, content: bytes, name: str = "grand-livre.csv") -> dict[str, Any]:
    res = client.post("/api/v1/imports", data={"kind": "COSTS"}, files={"file": (name, content, "text/csv")})
    assert res.status_code == 201, res.text
    job: dict[str, Any] = res.json()
    return job


def preview(client: TestClient, job: dict[str, Any], **options: Any) -> dict[str, Any]:
    """The preview's report — also when every row is refused, where it comes with the refusal."""
    res = client.post(f"/api/v1/imports/{job['id']}/validate", json={"mapping": job["mapping"], **options})
    if res.status_code == 422 and res.json()["code"] == "NO_VALID_ROWS":
        report: dict[str, Any] = res.json()["report"]
        return report
    assert res.status_code == 200, res.text
    report = res.json()["report"]
    return report


def commit(client: TestClient, job: dict[str, Any]) -> dict[str, Any]:
    res = client.post(f"/api/v1/imports/{job['id']}/commit", json={})
    assert res.status_code == 200, res.text
    body: dict[str, Any] = res.json()
    return body


def by_row(issues: list[dict[str, Any]]) -> dict[int, str]:
    return {issue["row"]: issue["code"] for issue in issues}


def costs_on(client: TestClient, target: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = client.get("/api/v1/costs", params={"target_id": target}).json()
    return found


# ---------------------------------------------------------------------------- what is read


def test_a_ledger_lands_on_its_boxes_bills_and_orders_with_its_types_read_or_inferred(
    client: TestClient, world: dict[str, str]
) -> None:
    job = upload(client, ledger(
        "12/03/2026;TRANSITEX;F-1;Fret maritime;;3 000,00 €;;MSCU4821994;;",
        "12/03/2026;TRANSITEX;F-1;THC destination;Manutention portuaire (THC);285,00;EUR;MSCU4821994;;",
        "12/03/2026;TRANSITEX;F-1;THC destination;Manutention portuaire (THC);285,00;EUR;MSCU4821994;;",
        "13/03/2026;TRANSPORTS LEMAIRE;L-9;Camionnage MSCU4821994 Le Havre;;425,00;EUR;;;",
        "14/03/2026;TRANSITEX;F-2;Frais de dossier;;45,00;EUR;;BL-C;",
        "14/03/2026;TRANSITEX;F-2;Frais de dossier;;60,00;EUR;;bl-a;",
        "15/03/2026;DOUANE;D-1;Droits de douane;;120,00;EUR;;;PO-1",
    ))  # fmt: skip
    report = preview(client, job)
    assert (report["errors"], report["valid_rows"], report["costs_created"]) == ([], 7, 6)
    assert by_row(report["warnings"]) == {5: "TARGET_FROM_LABEL"}
    assert report["money"]["total_base"] == "4220.00"
    assert {row["cost_type"]: (row["rows"], row["total_base"]) for row in report["money"]["by_type"]} == {
        "BL_FEE": (2, "105.00"),
        "CUSTOMS_DUTY": (1, "120.00"),
        "DRAYAGE": (1, "425.00"),
        "OCEAN_FREIGHT": (1, "3000.00"),
        "THC": (2, "570.00"),  # two identical lines of one invoice are one cost
    }
    assert report["purchase_orders_created"] is None
    assert costs_on(client, world["MSCU4821994"]) == []  # a preview writes nothing

    committed = commit(client, job)
    assert committed["can_undo"] is True
    on_box = {c["cost_type"]: c for c in costs_on(client, world["MSCU4821994"])}
    assert (on_box["THC"]["amount"], on_box["THC"]["notes"]) == ("570.00", "From grand-livre.csv rows 3, 4")
    alone = costs_on(client, world["CSQU3054383"])  # a bill with one box is that box
    assert [(c["scope"], c["amount"]) for c in alone] == [("CONTAINER", "45.00")]
    shared = costs_on(client, world["BL-A"])  # a bill with two boxes keeps the bill
    assert [(c["scope"], c["amount"]) for c in shared] == [("SHIPMENT", "60.00")]
    assert [c["scope"] for c in costs_on(client, world["PO-1"])] == ["PO"]


def test_what_cannot_be_read_right_is_refused_by_name(client: TestClient, world: dict[str, str]) -> None:
    taxed = upload(client, ledger("12/03/2026;X;F-1;THC;;285,00;EUR;MSCU4821994;;",
                                  header=HEADER.replace("Montant HT", "Montant TTC")))  # fmt: skip
    assert "amount" not in taxed["mapping"]  # never proposed as the amount...
    mapping = {**taxed["mapping"], "amount": "Montant TTC"}  # ...and refused when a person maps it
    res = client.post(f"/api/v1/imports/{taxed['id']}/validate", json={"mapping": mapping})
    assert (res.status_code, res.json()["code"]) == (422, "AMOUNT_INCLUDES_VAT")

    job = upload(client, ledger(
        "12/03/2026;X;F-1;THC;;285,00;EUR;MSKU1234565;;",       # 2: a box nobody has
        "12/03/2026;X;F-2;THC;;285,00;EUR;;BL-Z;",              # 3: a bill nobody has
        "12/03/2026;X;F-3;THC;;285,00;EUR;;;PO-9",              # 4: an order nobody has
        "12/03/2026;X;F-4;THC du mois;;285,00;EUR;;;",          # 5: nothing to land on
        "12/03/2026;X;F-5;Débours;;285,00;EUR;MSCU4821994;;",   # 6: several charges in one
        "12/03/2026;X;F-6;Fret + THC;;285,00;EUR;MSCU4821994;;",
        "12/03/2026;X;F-7;THC;;100,00 $;EUR;MSCU4821994;;",     # 8: dollars in a euro column
        "12/03/2026;X;F-8;THC;;100,00;JPY;MSCU4821994;;",       # 9: no rate for that currency
        "12/03/2026;X;F-9;Prestation spéciale;;80,00;EUR;MSCU4821994;;",
        "12/03/2026;X;F-10;Prestation spéciale;;20,00;EUR;TGHU7245086;;",
        "12/03/2026;X;F-11;THC;Transport express;20,00;EUR;TGHU7245086;;",
    ))  # fmt: skip
    report = preview(client, job)
    assert by_row(report["errors"]) == {
        2: "UNKNOWN_CONTAINER",
        3: "UNKNOWN_SHIPMENT",
        4: "UNKNOWN_ORDER",
        5: "NO_TARGET",
        6: "COST_TYPE_AMBIGUOUS",
        7: "COST_TYPE_AMBIGUOUS",
        8: "AMOUNT_CURRENCY_MISMATCH",
        9: "FX_RATE_UNAVAILABLE",
        10: "COST_TYPE_UNKNOWN",
        11: "COST_TYPE_UNKNOWN",
        12: "COST_TYPE_UNKNOWN",  # a type column that names no type
    }
    assert report["unknown_labels"] == [{"label": "Prestation spéciale", "rows": 2, "total_base": "100.00"}]

    typed = preview(client, job, label_types={"Prestation spéciale": "INSPECTION"})
    assert 10 not in by_row(typed["errors"]) and 11 not in by_row(typed["errors"])
    assert typed["costs_created"] == 2


def test_a_negative_line_cancels_its_twin_or_is_set_aside_and_counted(
    client: TestClient, world: dict[str, str]
) -> None:
    job = upload(client, ledger(
        "12/03/2026;TRANSITEX;F-1;THC;;285,00;EUR;MSCU4821994;;",
        "12/03/2026;TRANSITEX;AV-1;THC;;-285,00;EUR;MSCU4821994;;",  # cancels the line above
        "12/03/2026;TRANSITEX;AV-2;Remise fret;Fret maritime;(50,00);EUR;MSCU4821994;;",  # a refund
        "12/03/2026;TRANSITEX;F-3;Fret maritime;;3 000,00;EUR;MSCU4821994;;",
    ))  # fmt: skip
    report = preview(client, job)
    assert by_row(report["errors"]) == {2: "REVERSED_IN_FILE", 3: "REVERSED_IN_FILE"}
    assert report["reversed_in_file"] == 1
    assert report["credit_notes_skipped"] == [
        {"row": 4, "cost_date": "2026-03-12", "vendor": "TRANSITEX", "invoice_number": "AV-2",
         "amount": "-50.00", "currency": "EUR", "amount_base": "-50.00"}
    ]  # fmt: skip
    assert (report["credit_notes_skipped_base"], report["costs_created"]) == ("-50.00", 1)


# ---------------------------------------------------------------------------- the same line never twice


def typed(client: TestClient, target: str, cost_type: str, amount: str, **extra: Any) -> dict[str, Any]:
    body = {"scope": extra.pop("scope", "CONTAINER"), "target_id": target, "cost_type": cost_type,
            "amount": amount, "currency": "EUR", "cost_date": "2026-03-11", **extra}  # fmt: skip
    res = client.post("/api/v1/costs", json=body)
    assert res.status_code == 201, res.text
    made: dict[str, Any] = res.json()
    return made


def test_what_the_books_already_hold_is_refused_and_a_person_may_overrule_a_neighbour(
    client: TestClient, db: Session, org: Organization, world: dict[str, str]
) -> None:
    typed(
        client, world["MSCU4821994"], "OCEAN_FREIGHT", "3000.00", vendor="Transitex SAS", invoice_number="F 1"
    )
    typed(client, world["TGHU7245086"], "THC", "250.00", vendor="TERMINAL", invoice_number="T-7")
    waiting = client.post(
        "/api/v1/invoices", files={"file": ("f.pdf", make_pdf(FRENCH_ONE_CONTAINER), "application/pdf")}
    ).json()["id"]
    handlers.extract_invoice(db, org.id, uuid.UUID(waiting))  # FA-2026-0912, waiting in review

    job = upload(client, ledger(
        "12/03/2026;TRANSITEX;F-1;THC;;285,00;EUR;MSCU4821994;;",  # the invoice F-1 is in the books
        "12/03/2026;TRANSITEX;FA-2026-0912;THC;;275,00;EUR;CSQU3054383;;",  # its PDF is in the inbox
        "12/03/2026;TRANSITEX;F-8;THC;;250,00;EUR;TGHU7245086;;",  # a handling already on that box
    ))  # fmt: skip
    report = preview(client, job)
    assert by_row(report["errors"]) == {
        2: "INVOICE_ALREADY_RECORDED",
        3: "INVOICE_IN_INBOX",
        4: "DUPLICATE_COST",
    }
    assert (report["duplicates"], report["duplicates_base"]) == (3, "810.00")
    overruled = preview(client, job, force_duplicates=True)
    assert by_row(overruled["errors"]) == {2: "INVOICE_ALREADY_RECORDED", 3: "INVOICE_IN_INBOX"}
    commit(client, job)
    history = client.get("/api/v1/audit-log", params={"entity_id": job["id"]}).json()["entries"]
    (entry,) = [e for e in history if e["action"] == "import.committed"]
    assert entry["after"]["force_duplicates"] is True and len(entry["after"]["cost_ids"]) == 1


def test_an_estimate_on_the_line_s_target_is_replaced_and_any_other_is_left_to_a_person(
    client: TestClient, world: dict[str, str]
) -> None:
    replaced = typed(client, world["MSCU4821994"], "THC", "250.00", status="ESTIMATE")
    typed(client, world["TGHU7245086"], "DRAYAGE", "400.00", status="ESTIMATE")
    typed(client, world["TGHU7245086"], "DRAYAGE", "420.00", status="ESTIMATE")
    typed(client, world["BL-C"], "OCEAN_FREIGHT", "3000.00", status="ESTIMATE", scope="SHIPMENT")
    job = upload(client, ledger(
        "12/03/2026;TRANSITEX;F-1;THC;;285,00;EUR;MSCU4821994;;",
        "12/03/2026;TRANSITEX;F-2;Camionnage;;410,00;EUR;TGHU7245086;;",
        "12/03/2026;TRANSITEX;F-3;Fret maritime;;3 100,00;EUR;CSQU3054383;;",
    ))  # fmt: skip
    report = preview(client, job)
    assert by_row(report["errors"]) == {3: "SEVERAL_ESTIMATES", 4: "ESTIMATE_OTHER_SCOPE"}
    assert (report["estimates_replaced"], report["estimates_replaced_base"]) == (1, "250.00")
    commit(client, job)
    (thc,) = [c for c in costs_on(client, world["MSCU4821994"]) if c["status"] == "ACTUAL"]
    assert thc["supersedes_cost_id"] == replaced["id"]


def test_a_preview_binds_its_commit_and_the_same_ledger_is_never_read_twice(
    client: TestClient, world: dict[str, str]
) -> None:
    first = ledger("12/03/2026;TRANSITEX;F-1;THC;;285,00;EUR;MSCU4821994;;")
    job = upload(client, first)
    refused = client.post(f"/api/v1/imports/{job['id']}/commit", json={})
    assert (refused.status_code, refused.json()["code"]) == (409, "PREVIEW_REQUIRED")
    preview(client, job)
    commit(client, job)
    again = client.post(
        "/api/v1/imports", data={"kind": "COSTS"}, files={"file": ("g.csv", first, "text/csv")}
    )
    assert (again.status_code, again.json()["code"], again.json()["existing_id"]) == (
        409,
        "FILE_ALREADY_IMPORTED",
        job["id"],
    )

    # The next month's export of the same ledger: what is already in is recognised and left alone.
    grown = upload(
        client,
        ledger(
            "12/03/2026;TRANSITEX;F-1;THC;;285,00;EUR;MSCU4821994;;",
            "13/03/2026;TRANSITEX;F-2;Fret maritime;;3 000,00;EUR;MSCU4821994;;",
        ),
    )
    report = preview(client, grown)
    assert (report["costs_skipped"], report["costs_created"], report["errors"]) == (1, 1, [])
    # Between the preview and the commit, the freight gets keyed in by hand: the same file would now
    # do something else, and the person is shown what before anything is written.
    typed(client, world["MSCU4821994"], "OCEAN_FREIGHT", "3000.00", vendor="TRANSITEX", invoice_number="F-2")
    changed = client.post(f"/api/v1/imports/{grown['id']}/commit", json={})
    assert (changed.status_code, changed.json()["code"]) == (409, "PREVIEW_CHANGED")
    assert by_row(changed.json()["report"]["errors"]) == {3: "INVOICE_ALREADY_RECORDED"}
    assert client.get(f"/api/v1/imports/{grown['id']}").json()["report"]["costs_created"] == 0


def test_a_costs_file_is_taken_back_whole_and_once(client: TestClient, world: dict[str, str]) -> None:
    estimate = typed(client, world["MSCU4821994"], "THC", "250.00", status="ESTIMATE")
    job = upload(client, ledger(THC_F1, FREIGHT_F1))
    preview(client, job)
    commit(client, job)
    assert [j["can_undo"] for j in client.get("/api/v1/imports").json()] == [True]

    undone = client.delete(f"/api/v1/imports/{job['id']}")
    assert undone.status_code == 200, undone.text
    assert undone.json() == {"costs_deleted": 2, "estimates_reopened": 1}
    assert [c["id"] for c in costs_on(client, world["MSCU4821994"])] == [estimate["id"]]  # standing again
    again = client.delete(f"/api/v1/imports/{job['id']}")
    assert (again.status_code, again.json()["code"]) == (409, "IMPORT_ALREADY_UNDONE")
    assert client.get(f"/api/v1/imports/{job['id']}").json()["can_undo"] is False
    # and the same file can come in again once taken back
    assert upload(client, ledger(THC_F1, FREIGHT_F1))


def test_a_file_that_is_not_costs_is_not_taken_back(client: TestClient, world: dict[str, str]) -> None:
    orders = client.post(
        "/api/v1/imports",
        data={"kind": "PURCHASE_ORDERS"},
        files={"file": ("po.csv", "N° commande;Quantité;Prix unitaire\nPO-9;10;5\n".encode(), "text/csv")},
    ).json()
    client.post(f"/api/v1/imports/{orders['id']}/commit", json={})
    refused = client.delete(f"/api/v1/imports/{orders['id']}")
    assert (refused.status_code, refused.json()["code"]) == (422, "IMPORT_NOT_UNDOABLE")


# ---------------------------------------------------------------------------- the money it makes


def test_the_ledger_s_duty_is_weighed_against_the_customs_value_its_own_freight_makes(
    client: TestClient, world: dict[str, str]
) -> None:
    """Tyres at 10 %, a jack at 0 %, freight 3 000 € and duty 250 € in the same file: 10 % of
    (1 000 + 1 500). Weighed without the file's freight the jack would pay half of it."""
    job = upload(
        client, ledger("15/03/2026;DOUANE;D-1;Droits de douane;;250,00;EUR;MSCU4821994;;", FREIGHT_F1)
    )
    preview(client, job)
    commit(client, job)
    (duty,) = [c for c in costs_on(client, world["MSCU4821994"]) if c["cost_type"] == "CUSTOMS_DUTY"]
    assert duty["allocation_method"] == "BY_THEORETICAL_DUTY"


def test_what_the_audit_finds_on_an_inferred_type_is_a_question(
    client: TestClient, world: dict[str, str]
) -> None:
    """The same handling twice from one forwarder is a fact — unless the type was read in the label:
    then it may be two different charges the label words alike."""
    job = upload(client, ledger("12/03/2026;TRANSITEX;F-1;THC;;285,00;EUR;MSCU4821994;;",
                                "20/03/2026;TRANSITEX;F-9;THC;;285,00;EUR;MSCU4821994;;"))  # fmt: skip
    preview(client, job)
    commit(client, job)
    findings = client.get("/api/v1/reports/audit", params=MARCH).json()["findings"]
    (duplicate,) = [f for f in findings if f["code"] == "DUPLICATE_CHARGE"]
    assert (duplicate["confidence"], Decimal(duplicate["amount"])) == ("to_check", Decimal("285.00"))


# ---------------------------------------------------------------------------- at the size of a ledger


def test_a_year_of_ledger_is_previewed_committed_and_recognised_within_budget(client: TestClient) -> None:
    """Two thousand lines on forty boxes: a preview, its commit, and next month's export of the same
    ledger — every line recognised — each in seconds, not minutes. The rules read the books once."""
    assert client.get("/api/v1/organization").status_code == 200
    line = {"line_no": 1, "sku": "A", "quantity": "100000", "unit_price": "10", "duty_rate": "0.045"}
    po = client.post(
        "/api/v1/purchase-orders", json={"po_number": "PO-1", "currency": "EUR", "lines": [line]}
    ).json()
    boxes = []
    for n in range(40):
        body = f"MSCU{100000 + n:06d}"
        number = body + str(check_digit(body))
        box = client.post("/api/v1/containers", json={"container_number": number}).json()
        client.patch(f"/api/v1/containers/{box['id']}", json={"discharged_at": "2026-03-10T12:00:00Z"})
        loads = [{"po_line_id": po["lines"][0]["id"], "quantity": "100"}]
        client.put(f"/api/v1/containers/{box['id']}/loads", json=loads)
        boxes.append(number)
    kinds = ["THC", "Fret maritime", "Camionnage", "Dédouanement", "Droits de douane"]
    rows = [
        f"12/03/2026;V{i % 7};F-{i};{kinds[i % 5]};;{100 + i % 50},00;EUR;{boxes[i % 40]};;"
        for i in range(2000)
    ]
    content = ledger(*rows)

    def timed(action: Any) -> tuple[float, Any]:
        started = time.perf_counter()
        result = action()
        return time.perf_counter() - started, result

    job = upload(client, content)
    previewing, report = timed(lambda: preview(client, job, force_duplicates=True))
    committing, _ = timed(lambda: commit(client, job))
    grown = upload(client, ledger(*rows, f"13/03/2026;V1;F-9999;THC;;120,00;EUR;{boxes[0]};;"))
    recognising, again = timed(lambda: preview(client, grown, force_duplicates=True))
    assert (report["costs_created"], again["costs_skipped"], again["costs_created"]) == (2000, 2000, 1)
    measured = {"preview": previewing, "commit": committing, "re-import preview": recognising}
    print("\n" + "\n".join(f"{seconds:6.2f} s  {step}" for step, seconds in measured.items()))
    late = {step: round(seconds, 2) for step, seconds in measured.items() if seconds > 8.0}
    assert not late, f"over budget: {late}"
