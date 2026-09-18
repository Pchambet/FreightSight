"""A cost comes in by several doors — typed by hand, confirmed from an invoice, estimated from the rate
cards — and lands the same way through each: the same duty method, one cost per charge and target, and
the same invoice never twice, whatever spelling each copy came with."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from invoice_fixtures import FRENCH_ONE_CONTAINER, FRENCH_TWO_CONTAINERS
from pdfs import make_pdf
from sqlalchemy.orm import Session

from app.domain.costing.entry import normalize_invoice_number, normalize_vendor, same_invoice
from app.domain.models import Organization
from app.jobs import handlers

DUTY = "CUSTOMS_DUTY"


@pytest.fixture
def org(client: TestClient, db: Session, org_id: uuid.UUID) -> Organization:
    assert client.get("/api/v1/organization").status_code == 200
    organization = db.get(Organization, org_id)
    assert organization is not None
    return organization


def container_with(client: TestClient, number: str, lines: Sequence[tuple[str, str | None]]) -> str:
    """A container discharged in March holding one order: a hundred units worth 1 000 € per line, each
    with its duty rate (None: the line has none)."""
    body = {
        "po_number": f"PO-{number}",
        "currency": "EUR",
        "lines": [
            {"line_no": n, "sku": sku, "quantity": "100", "unit_price": "10",
             **({"duty_rate": rate} if rate is not None else {})}
            for n, (sku, rate) in enumerate(lines, start=1)
        ],
    }  # fmt: skip
    po = client.post("/api/v1/purchase-orders", json=body).json()
    box = client.post("/api/v1/containers", json={"container_number": number}).json()
    assert client.patch(
        f"/api/v1/containers/{box['id']}", json={"discharged_at": "2026-03-10T08:00:00Z"}
    ).is_success
    loads = [{"po_line_id": line["id"], "quantity": "100"} for line in po["lines"]]
    assert client.put(f"/api/v1/containers/{box['id']}/loads", json=loads).status_code == 200
    return str(box["id"])


def duty_by_sku(client: TestClient, box: str) -> dict[str, Decimal]:
    report = client.get(f"/api/v1/landed-costs/containers/{box}").json()
    return {line["sku"]: Decimal(line["by_cost_type"].get(DUTY, "0")) for line in report["lines"]}


def typed(client: TestClient, box: str, cost_type: str, amount: str, **extra: Any) -> dict[str, Any]:
    body = {"scope": "CONTAINER", "target_id": box, "cost_type": cost_type, "amount": amount,
            "currency": "EUR", "cost_date": "2026-03-12", **extra}  # fmt: skip
    res = client.post("/api/v1/costs", json=body)
    assert res.status_code == 201, res.text
    made: dict[str, Any] = res.json()
    return made


def read_invoice(
    client: TestClient, db: Session, org: Organization, text: list[str]
) -> tuple[str, list[dict[str, Any]]]:
    invoice_id = client.post(
        "/api/v1/invoices", files={"file": ("facture.pdf", make_pdf(text), "application/pdf")}
    ).json()["id"]
    assert handlers.extract_invoice(db, org.id, uuid.UUID(invoice_id)) == "NEEDS_REVIEW"
    lines: list[dict[str, Any]] = client.get(f"/api/v1/invoices/{invoice_id}").json()["lines"]
    return invoice_id, lines


def accept(client: TestClient, invoice_id: str, line: dict[str, Any], **patch: Any) -> None:
    res = client.patch(f"/api/v1/invoices/{invoice_id}/lines/{line['id']}", json={"accepted": True, **patch})
    assert res.status_code == 200, res.text


# ---------------------------------------------------------------------------- the duty method


def test_a_jack_at_zero_per_cent_pays_no_duty_whichever_door_the_duty_came_in_by(
    client: TestClient, db: Session, org: Organization
) -> None:
    """Tyres at 4.5 % and a jack at 0 % in one box: customs took 4.5 % of the tyres. Spread by customs
    value the jack would pay half of it. Typed, estimated or confirmed, it now pays nothing."""
    typed_box = container_with(client, "TCLU1234565", [("TYRE", "0.045"), ("JACK", "0")])
    assert typed(client, typed_box, DUTY, "45.00")["allocation_method"] == "BY_THEORETICAL_DUTY"
    assert duty_by_sku(client, typed_box) == {"TYRE": Decimal("45.00"), "JACK": Decimal("0.00")}

    estimated_box = container_with(client, "TGHU7245081", [("TYRE", "0.045"), ("JACK", "0")])
    estimates = client.post(f"/api/v1/containers/{estimated_box}/estimates").json()["created"]
    (estimate,) = [e for e in estimates if e["cost_type"] == DUTY]
    assert (estimate["amount"], estimate["allocation_method"]) == ("45.00", "BY_THEORETICAL_DUTY")
    assert duty_by_sku(client, estimated_box)["JACK"] == Decimal("0.00")

    confirmed_box = container_with(client, "MSCU4821990", [("TYRE", "0.045"), ("JACK", "0")])
    invoice_id, lines = read_invoice(client, db, org, FRENCH_ONE_CONTAINER)
    clearance = next(line for line in lines if line["description"].startswith("Dedouanement"))
    accept(client, invoice_id, clearance, cost_type=DUTY, amount="45.00")
    assert client.post(f"/api/v1/invoices/{invoice_id}/confirm").status_code == 200
    on_box = client.get("/api/v1/costs", params={"target_id": confirmed_box}).json()
    (duty,) = [c for c in on_box if c["cost_type"] == DUTY]
    assert duty["allocation_method"] == "BY_THEORETICAL_DUTY"
    assert duty_by_sku(client, confirmed_box) == {"TYRE": Decimal("45.00"), "JACK": Decimal("0.00")}


def test_rates_that_are_all_zero_leave_the_duty_spread_by_customs_value(client: TestClient) -> None:
    """Nothing to spread on: theoretical duty would leave the whole duty unallocated."""
    box = container_with(client, "TCLU1234565", [("A", "0"), ("B", "0")])
    assert typed(client, box, DUTY, "50.00")["allocation_method"] == "BY_CIF_VALUE"
    assert duty_by_sku(client, box) == {"A": Decimal("25.00"), "B": Decimal("25.00")}


def test_default_zeros_that_do_not_explain_the_duty_paid_are_not_trusted_to_split_it(
    client: TestClient,
) -> None:
    """An ERP that writes 0 % on every product: nine lines at 0 %, one at 4.5 %, and customs took 450 €
    — ten times what the rates explain. By theoretical duty the one rated line would carry all 450."""
    box = container_with(client, "TCLU1234565", [(f"L{n}", "0") for n in range(9)] + [("RATED", "0.045")])
    assert typed(client, box, DUTY, "450.00")["allocation_method"] == "BY_CIF_VALUE"
    assert set(duty_by_sku(client, box).values()) == {Decimal("45.00")}
    # and within the guard the rates are trusted again
    near = container_with(client, "TGHU7245081", [("TYRE", "0.045"), ("JACK", "0")])
    assert typed(client, near, DUTY, "52.00")["allocation_method"] == "BY_THEORETICAL_DUTY"  # 45 + 15.6 %


# ---------------------------------------------------------------------------- one invoice, many lines


def test_a_freight_and_its_bunker_surcharge_on_one_invoice_are_one_cost(
    client: TestClient, db: Session, org: Organization
) -> None:
    """Two lines of one type on one container: it was a database error, a 500 on an ordinary invoice."""
    box = container_with(client, "MSCU4821990", [("TYRE", "0.045")])
    invoice_id, lines = read_invoice(client, db, org, FRENCH_ONE_CONTAINER)
    freight = next(line for line in lines if line["cost_type"] == "OCEAN_FREIGHT")
    baf = next(line for line in lines if line["cost_type"] == "THC")  # read as THC, corrected by the reviewer
    accept(client, invoice_id, freight)
    accept(client, invoice_id, baf, cost_type="OCEAN_FREIGHT")

    confirmed = client.post(f"/api/v1/invoices/{invoice_id}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["costs_created"] == 1
    (cost,) = client.get("/api/v1/costs", params={"target_id": box}).json()
    assert (cost["cost_type"], cost["amount"]) == ("OCEAN_FREIGHT", "3275.00")
    assert cost["notes"].endswith("lines 1, 2")
    after = client.get(f"/api/v1/invoices/{invoice_id}").json()["lines"]
    assert {line["cost_id"] for line in after if line["accepted"]} == {cost["id"]}


def test_one_invoice_billing_the_same_charge_on_two_containers_is_confirmed(
    client: TestClient, db: Session, org: Organization
) -> None:
    """The handling of each box of a bill of lading, one line per box: the other shape that failed."""
    first = container_with(client, "MSCU4821990", [("TYRE", "0.045")])
    second = container_with(client, "TGHU7245081", [("TYRE", "0.045")])
    invoice_id, lines = read_invoice(client, db, org, FRENCH_TWO_CONTAINERS)
    handlings = [line for line in lines if line["cost_type"] == "THC"]
    assert {line["target_id"] for line in handlings} == {first, second}
    for line in handlings:
        accept(client, invoice_id, line)
    confirmed = client.post(f"/api/v1/invoices/{invoice_id}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["costs_created"] == 2


# ---------------------------------------------------------------------------- the same invoice twice


def test_one_invoice_is_recognised_under_any_spelling() -> None:
    assert normalize_vendor("Transitex SAS") == normalize_vendor("TRANSITEX") == "transitex"
    assert normalize_vendor("KUEHNE + NAGEL SAS") == normalize_vendor("Kuehne Nagel") == "kuehnenagel"
    assert (
        normalize_invoice_number("FA-2026-0412") == normalize_invoice_number("fa 2026 0412") == "FA20260412"
    )
    assert same_invoice("TRANSITEX", "F-0412", "Transitex SAS", "F0412")
    assert same_invoice(None, "F-0412", "Transitex SAS", "F0412")  # one copy names no forwarder
    assert not same_invoice("TRANSITEX", "F-0412", "SCHELDE NV", "F0412")  # two forwarders' "0412"
    assert not same_invoice("TRANSITEX", "", "TRANSITEX", "")  # no number, nothing to say


def test_an_invoice_already_in_the_books_is_refused_whatever_its_spelling_and_type(
    client: TestClient, db: Session, org: Organization
) -> None:
    """Keyed in from the forwarder's statement on Monday — its total, as one freight — then its PDF
    confirmed on Tuesday: every line of it would count twice, the handling included. Not a charge
    that looks like another, which a person may overrule: the same document."""
    box = container_with(client, "MSCU4821990", [("TYRE", "0.045")])
    typed(client, box, "OCEAN_FREIGHT", "3830.00", vendor="Transitex", invoice_number="FA 2026 0912")
    invoice_id, lines = read_invoice(client, db, org, FRENCH_ONE_CONTAINER)
    accept(client, invoice_id, next(line for line in lines if line["cost_type"] == "THC"))

    for payload in (None, {"force": True}):
        refused = client.post(f"/api/v1/invoices/{invoice_id}/confirm", json=payload)
        assert (refused.status_code, refused.json()["code"]) == (422, "INVOICE_ALREADY_RECORDED")
    (seen,) = refused.json()["errors"]
    assert seen["message"].startswith("@recorded|OCEAN_FREIGHT|Transitex|FA 2026 0912|3830.00|CONTAINER|")


def test_the_same_invoice_entered_twice_is_never_a_charge_billed_twice(client: TestClient) -> None:
    """A double entry of ours is not the forwarder's doing: the audit does not claim it."""
    box = container_with(client, "MSCU4821990", [("TYRE", "0.045")])
    typed(client, box, "THC", "260.00", vendor="TRANSITEX", invoice_number="F-0412")
    typed(client, box, "THC", "260.00", vendor="Transitex SAS", invoice_number="F0412")
    audit = client.get(
        "/api/v1/reports/audit", params={"period_from": "2026-03-01", "period_to": "2026-03-31"}
    )
    assert [f for f in audit.json()["findings"] if f["code"] == "DUPLICATE_CHARGE"] == []
