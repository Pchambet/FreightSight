"""The tester's kit (`docs/demo/kit-testeur`), loaded the way its guide says, file by file.

GUIDE.md sends someone who has never seen the application through the files of a made-up importer and
quotes what each screen will show. This loads the very files committed next to it — the four CSVs and
the two PDFs as Chrome printed them — and holds the figures the guide quotes, so that the guide and the
screens can never tell a tester two different things. Nothing here depends on the day it runs: the kit's
dates are those of the day it was generated, and the bell that rings on the day of an import is held by
`test_imports_containers`, on dates taken from today."""

from __future__ import annotations

import csv
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from previews import commit_previewed
from sqlalchemy.orm import Session

from app.domain.models import Organization
from app.jobs import handlers

KIT = Path(__file__).resolve().parents[2] / "docs" / "demo" / "kit-testeur"
L1, L2, H1 = "MSCU6702211", "MSCU6715564", "MSCU6614208"


def rows(name: str) -> list[dict[str, str]]:
    with (KIT / name).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def day(text: str) -> date:
    d, m, y = text.split("/")
    return date(int(y), int(m), int(d))


def load(client: TestClient, kind: str, name: str) -> dict[str, Any]:
    job = client.post(
        "/api/v1/imports", data={"kind": kind}, files={"file": (name, (KIT / name).read_bytes(), "text/csv")}
    ).json()
    previewed = client.post(f"/api/v1/imports/{job['id']}/validate", json={"mapping": job["mapping"]})
    assert previewed.status_code == 200, previewed.text
    assert previewed.json()["report"]["errors"] == [], (name, previewed.json()["report"]["errors"])
    committed = commit_previewed(client, job["id"])
    assert committed.status_code == 200, committed.text
    report: dict[str, Any] = committed.json()["report"]
    return report


def read(client: TestClient, db: Session, org: Organization, name: str) -> dict[str, Any]:
    invoice_id = client.post(
        "/api/v1/invoices", files={"file": (name, (KIT / name).read_bytes(), "application/pdf")}
    ).json()["id"]
    assert handlers.extract_invoice(db, org.id, uuid.UUID(invoice_id)) == "NEEDS_REVIEW"
    invoice: dict[str, Any] = client.get(f"/api/v1/invoices/{invoice_id}").json()
    for line in invoice["lines"]:
        assert client.patch(
            f"/api/v1/invoices/{invoice_id}/lines/{line['id']}", json={"accepted": True}
        ).is_success
    return invoice


def unit_costs(report: dict[str, Any]) -> dict[str, str]:
    return {line["sku"]: line["unit_landed_cost"] for line in report["lines"]}


@pytest.fixture
def org(client: TestClient, db: Session, org_id: uuid.UUID) -> Organization:
    assert client.get("/api/v1/organization").status_code == 200
    organization = db.get(Organization, org_id)
    assert organization is not None
    return organization


def test_the_tester_s_kit_shows_every_figure_its_guide_promises(
    client: TestClient, db: Session, org: Organization
) -> None:
    # Act 1 — the four files, in the guide's order, each clean.
    assert load(client, "PRODUCTS", "1-tarif.csv")["products_created"] == 5
    orders = load(client, "PURCHASE_ORDERS", "2-commandes.csv")
    assert (orders["purchase_orders_created"], orders["lines_created"], orders["suppliers_created"]) == (
        11,
        14,
        3,
    )
    tracking = load(client, "CONTAINERS", "3-suivi-conteneurs.csv")
    assert (tracking["containers_created"], tracking["loads_created"], tracking["po_split"]) == (10, 14, 0)
    assert [w["code"] for w in tracking["warnings"]] == ["CLOCK_LEFT_RUNNING"]  # L1, still at the terminal
    ledger = load(client, "COSTS", "4-frais-trimestre.csv")
    assert (ledger["costs_created"], ledger["money"]["total_base"], ledger["credit_notes_skipped_base"]) == (
        42,
        "45758.53",
        "-80.00",
    )
    assert {t["cost_type"]: t["total_base"] for t in ledger["money"]["by_type"]} == {
        "OCEAN_FREIGHT": "29510.00",
        "CUSTOMS_DUTY": "7878.53",
        "DRAYAGE": "4265.00",
        "THC": "2565.00",
        "CUSTOMS_BROKERAGE": "1160.00",
        "DEMURRAGE": "380.00",
    }

    # Act 2 — L1 counts its free days from the import on: its last free day is shown, and it is at risk.
    boxes = {c["container_number"]: c for c in client.get("/api/v1/containers").json()}
    discharged = next(
        day(r["Déchargé le"]) for r in rows("3-suivi-conteneurs.csv") if r["N° conteneur"] == L1
    )
    assert boxes[L1]["last_free_day"] == (discharged + timedelta(days=4)).isoformat()
    assert boxes[L1]["dnd_risk"] != "NONE"

    # Act 3 — L1's invoice: five lines read, each typed and on its container, confirmed whole.
    invoice = read(client, db, org, f"5-facture-transitaire-{L1}.pdf")
    issued = date.fromisoformat(invoice["invoice_date"])
    assert (invoice["invoice_number"], invoice["total_amount"]) == (f"MHL-{issued:%y}-0571", "5943.09")
    assert [(line["cost_type"], line["amount"]) for line in invoice["lines"]] == [
        ("OCEAN_FREIGHT", "3780.00"),
        ("THC", "285.00"),
        ("CUSTOMS_BROKERAGE", "145.00"),
        ("DRAYAGE", "440.00"),
        ("CUSTOMS_DUTY", "1293.09"),
    ]
    assert {line["target_id"] for line in invoice["lines"]} == {boxes[L1]["id"]}
    assert client.post(f"/api/v1/invoices/{invoice['id']}/confirm").status_code == 200
    l1 = client.get(f"/api/v1/landed-costs/containers/{boxes[L1]['id']}").json()
    assert (l1["totals"]["fob"], l1["totals"]["landed"]) == ("24440.00", "30383.09")
    assert unit_costs(l1) == {"PAR-300-BEI": "47.9145", "COU-45-ANT": "3.9455"}  # the parasol: +24 % on 38,50

    # The copy of an invoice the accountant already booked: every line flagged, confirmation refused.
    copy = read(client, db, org, "6-facture-transitaire-MSCU6678835.pdf")
    assert all("@duplicate_cost" in (line["notes"] or "") for line in copy["lines"])
    refused = client.post(f"/api/v1/invoices/{copy['id']}/confirm")
    assert (refused.status_code, refused.json()["code"]) == (422, "INVOICE_ALREADY_RECORDED")
    assert client.post(f"/api/v1/invoices/{copy['id']}/reject").is_success

    # Act 4 — freight by volume instead of value: the bulky parasol pays more, the dense lamp less.
    h1 = {"container_id": boxes[H1]["id"]}
    assert unit_costs(client.get(f"/api/v1/landed-costs/containers/{boxes[H1]['id']}").json()) == {
        "PAR-300-BEI": "45.0436",
        "LAM-SOL-4": "7.7048",
    }
    by_volume = {"OCEAN_FREIGHT": "BY_VOLUME", "THC": "BY_VOLUME", "DRAYAGE": "BY_VOLUME"}
    preview = client.post("/api/v1/landed-costs/preview", json=h1 | {"method_overrides": by_volume}).json()
    assert unit_costs(preview) == {"PAR-300-BEI": "46.1299", "LAM-SOL-4": "7.2703"}

    # Act 5 — the audit of the quarter the ledger covers, with the coefficient the company applies.
    first = min(day(r["Date du coût"]) for r in rows("4-frais-trimestre.csv"))
    start = date(first.year, (first.month - 1) // 3 * 3 + 1, 1)
    end = (start + timedelta(days=95)).replace(day=1) - timedelta(days=1)
    quarter = {"period_from": start.isoformat(), "period_to": end.isoformat()}
    preparation = client.get("/api/v1/reports/audit/preparation", params=quarter).json()["items"]
    assert [item["code"] for item in preparation if item["severity"] == "blocking"] == []
    assert client.patch("/api/v1/organization", json={"settings": {"assumed_coefficient": "1.12"}}).is_success
    audit = client.get("/api/v1/reports/audit", params=quarter).json()
    assert (
        audit["completeness"]["containers"],
        audit["completeness"]["fob"],
        audit["completeness"]["landed"],
    ) == (
        8,
        "189180.00",
        "234938.53",
    )
    assert (audit["coefficient"], audit["assumed_coefficient"]) == ("1.2419", "1.1200")
    assert {s["label"]: s["coefficient"] for s in audit["coefficient_by_supplier"]} == {
        "Ningbo Greenleaf Outdoor Co., Ltd": "1.2047",
        "Ningbo Suncraft Furniture Co., Ltd": "1.4623",
        "Saigon Teak Craft Co., Ltd": "1.1826",
    }
    chairs = next(m for m in audit["margins"] if m["sku"] == "CHA-ALU-ANT")
    assert (chairs["unit_landed"], chairs["margin_on_fob_pct"], chairs["margin_real_pct"]) == (
        "30.9531",
        "45.7",
        "20.6",
    )
    assert [(f["code"], f["confidence"], f["container_number"], f["amount"]) for f in audit["findings"]] == [
        ("DUPLICATE_CHARGE", "sure", "MSCU6662309", "285.00"),
        ("OUTLIER_CHARGE", "to_check", "MSCU6651475", "715.00"),
    ]
    assert [(d["container_number"], d["paid"]) for d in audit["demurrage"]] == [("CMAU4437293", "380.00")]
    # What a flat 1.12 left out of the quarter's cost: the sentence that sells the audit.
    assert audit["headline"]["gap_vs_assumed"] == "23056.93"

    # Act 6 — L2, still at sea: four rate cards, one click, a unit cost before any invoice.
    for cost_type, amount in (
        ("OCEAN_FREIGHT", "3650"),
        ("THC", "285"),
        ("CUSTOMS_BROKERAGE", "145"),
        ("DRAYAGE", "440"),
    ):
        card = {"cost_type": cost_type, "amount": amount, "currency": "EUR"}
        assert client.post("/api/v1/organization/rate-cards", json=card).status_code == 201
    estimated = client.post(f"/api/v1/containers/{boxes[L2]['id']}/estimates").json()
    assert sorted(c["cost_type"] for c in estimated["created"]) == [
        "CUSTOMS_BROKERAGE",
        "CUSTOMS_DUTY",
        "DRAYAGE",
        "OCEAN_FREIGHT",
        "THC",
    ]
    l2 = client.get(f"/api/v1/landed-costs/containers/{boxes[L2]['id']}").json()
    assert (l2["totals"]["estimated"], l2["totals"]["actual"], unit_costs(l2)) == (
        "4920.41",
        "0.00",
        {"CHA-ALU-ANT": "30.9623"},
    )
