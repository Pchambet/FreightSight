"""The audit of a period: every rule on a case built by hand, in both directions — it fires, and it
stays silent just under its threshold — because a finding in a document sold for 990 € must be a fact."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.domain.sample_history import DUPLICATE_THC_ON, NEVER_INVOICED_ON, OUTLIER_DRAYAGE_ON, VOYAGES

PERIOD = {"period_from": "2026-03-01", "period_to": "2026-03-31"}
LINE = {"line_no": 1, "sku": "A", "quantity": "100", "unit_price": "10"}


def landed(client: TestClient, number: str, day: str, quantity: str = "100") -> str:
    """A container discharged on `day`, carrying `quantity` units of a fresh order."""
    po = client.post(
        "/api/v1/purchase-orders",
        json={"po_number": f"PO-{number}", "currency": "EUR", "lines": [{**LINE, "quantity": quantity}]},
    ).json()
    box = client.post("/api/v1/containers", json={"container_number": number}).json()
    res = client.patch(
        f"/api/v1/containers/{box['id']}",
        json={"discharged_at": f"{day}T08:00:00Z", "milestone": "DISCHARGED"},
    )
    assert res.status_code == 200, res.text
    loads = [{"po_line_id": po["lines"][0]["id"], "quantity": quantity}]
    assert client.put(f"/api/v1/containers/{box['id']}/loads", json=loads).status_code == 200
    return str(box["id"])


def cost(client: TestClient, box: str, cost_type: str, amount: str, **extra: Any) -> dict[str, Any]:
    body = {"scope": "CONTAINER", "target_id": box, "cost_type": cost_type, "amount": amount,
            "currency": "EUR", "cost_date": "2026-03-15", **extra}  # fmt: skip
    res = client.post("/api/v1/costs", json=body)
    assert res.status_code == 201, res.text
    made: dict[str, Any] = res.json()
    return made


def audit(client: TestClient, **params: str) -> dict[str, Any]:
    res = client.get("/api/v1/reports/audit", params={**PERIOD, **params})
    assert res.status_code == 200, res.text
    body: dict[str, Any] = res.json()
    return body


def findings(client: TestClient, code: str) -> list[dict[str, Any]]:
    return [f for f in audit(client)["findings"] if f["code"] == code]


# ------------------------------------------------------------------------------- the rules


def test_the_same_charge_from_two_invoices_is_a_duplicate_and_three_per_cent_apart_is_not(
    client: TestClient,
) -> None:
    box = landed(client, "MSCU4821990", "2026-03-10")
    cost(client, box, "THC", "262.00", vendor="TRANSITEX SAS", invoice_number="FA-1")
    cost(client, box, "THC", "260.00", vendor="TERMINAL", invoice_number="TH-9")
    (found,) = findings(client, "DUPLICATE_CHARGE")
    assert (found["confidence"], found["amount"], found["container_number"]) == (
        "sure",
        "260.00",
        "MSCU4821990",
    )
    assert found["params"]["first_invoice"] == "FA-1" and len(found["cost_ids"]) == 2
    assert audit(client)["headline"]["recoverable_sure"] == "260.00"

    # 3 % apart is two different charges (one invoice carrying the same line twice cannot exist:
    # the database refuses it, see uq_costs_invoice_line)
    third = landed(client, "TCLU1234565", "2026-03-14")
    cost(client, third, "THC", "300.00", vendor="A", invoice_number="A-1")
    cost(client, third, "THC", "290.00", vendor="B", invoice_number="B-1")
    assert len(findings(client, "DUPLICATE_CHARGE")) == 1


def test_an_invoice_above_its_quote_is_a_fact_from_five_per_cent_and_fifty_euros(client: TestClient) -> None:
    box = landed(client, "MSCU4821990", "2026-03-10")
    quote = cost(client, box, "OCEAN_FREIGHT", "2000.00", status="ESTIMATE")
    invoice = cost(client, box, "OCEAN_FREIGHT", "2300.00", vendor="TRANSITEX SAS", invoice_number="FA-1")
    assert (
        client.patch(f"/api/v1/costs/{invoice['id']}", json={"supersedes_cost_id": quote["id"]}).status_code
        == 200
    )
    (found,) = findings(client, "ABOVE_QUOTE")
    assert (found["amount"], found["params"]["quoted"], found["params"]["share_pct"]) == (
        "300.00",
        "2000.00",
        "15.0",
    )

    # 4 % above is a bunker surcharge, not a claim
    other = landed(client, "TGHU7245081", "2026-03-12")
    quote2 = cost(client, other, "OCEAN_FREIGHT", "2000.00", status="ESTIMATE")
    invoice2 = cost(client, other, "OCEAN_FREIGHT", "2080.00", vendor="TRANSITEX SAS", invoice_number="FA-2")
    client.patch(f"/api/v1/costs/{invoice2['id']}", json={"supersedes_cost_id": quote2["id"]})
    assert len(findings(client, "ABOVE_QUOTE")) == 1


def test_a_charge_far_above_its_route_is_a_question_and_only_with_enough_peers(client: TestClient) -> None:
    voyage = client.post(
        "/api/v1/shipments",
        json={"reference": "BL-1", "origin_unlocode": "CNNGB", "destination_unlocode": "FRLEH"},
    ).json()
    boxes = []
    for n, day in enumerate(("2025-06-10", "2025-09-10", "2025-12-10", "2026-02-10", "2026-03-10")):
        box = landed(client, f"MSCU48219{n:02d}", day)
        client.patch(f"/api/v1/containers/{box}", json={"shipment_id": voyage["id"]})
        boxes.append(box)
    cost(client, boxes[4], "DRAYAGE", "1450.00", vendor="T", invoice_number="D-LAST")
    for box in boxes[:3]:
        cost(client, box, "DRAYAGE", "450.00", vendor="T", invoice_number=f"D-{box[:4]}")
    assert findings(client, "OUTLIER_CHARGE") == []  # a median of three is not a norm

    cost(client, boxes[3], "DRAYAGE", "450.00", vendor="T", invoice_number="D-4TH")
    (found,) = findings(client, "OUTLIER_CHARGE")
    assert (found["confidence"], found["amount"], found["basis"]) == ("to_check", "1000.00", 4)
    assert found["params"] == {
        "amount": "1450.00",
        "median": "450.00",
        "ratio": "3.2",
        "route": "CNNGB-FRLEH",
    }
    headline = audit(client)["headline"]
    assert (headline["recoverable_sure"], headline["recoverable_to_check"]) == ("0.00", "1000.00")


def test_duty_follows_the_goods_not_the_route_and_one_euro_is_one_finding(client: TestClient) -> None:
    """A box of engines pays more duty than a box of tyres on the same voyage: no outlier there. And
    a handling billed twice is a duplicate, not a duplicate plus a charge "far above the route"."""
    voyage = client.post(
        "/api/v1/shipments",
        json={"reference": "BL-1", "origin_unlocode": "CNNGB", "destination_unlocode": "FRLEH"},
    ).json()
    boxes = []
    for n, day in enumerate(("2025-06-10", "2025-09-10", "2025-12-10", "2026-02-10", "2026-03-10")):
        box = landed(client, f"MSCU48219{n:02d}", day)
        client.patch(f"/api/v1/containers/{box}", json={"shipment_id": voyage["id"]})
        boxes.append(box)
        cost(
            client, box, "CUSTOMS_DUTY", "300.00" if n < 4 else "3000.00", vendor="T", invoice_number=f"C-{n}"
        )
        cost(client, box, "THC", "260.00", vendor="T", invoice_number=f"T-{n}")
    cost(client, boxes[4], "THC", "262.00", vendor="TERMINAL", invoice_number="TH-9")
    codes = [f["code"] for f in audit(client)["findings"]]
    assert codes == ["DUPLICATE_CHARGE"]


def test_an_estimate_still_standing_two_months_after_landing_was_never_invoiced(client: TestClient) -> None:
    old = landed(client, "MSCU4821990", "2026-01-20")
    cost(client, old, "CUSTOMS_BROKERAGE", "120.00", status="ESTIMATE", cost_date="2026-01-20")
    fresh = landed(client, "TGHU7245081", "2026-03-20")
    cost(client, fresh, "CUSTOMS_BROKERAGE", "120.00", status="ESTIMATE")
    stale = [
        f
        for f in audit(client, period_from="2026-01-01")["findings"]
        if f["code"] == "ESTIMATE_NEVER_INVOICED"
    ]
    assert [(f["container_number"], f["amount"], f["params"]["days"]) for f in stale] == [
        ("MSCU4821990", "120.00", "70")
    ]


def test_what_the_engine_could_not_place_and_a_duty_without_a_rate_are_said(client: TestClient) -> None:
    po = client.post(
        "/api/v1/purchase-orders",
        json={"po_number": "PO-X", "currency": "EUR",
              "lines": [{"line_no": 1, "sku": "A", "quantity": "10", "unit_price": "10", "duty_rate": "0.05"},
                        {"line_no": 2, "sku": "B", "quantity": "10", "unit_price": "10"}]},
    ).json()  # fmt: skip
    box = client.post("/api/v1/containers", json={"container_number": "MSCU4821990"}).json()
    client.patch(f"/api/v1/containers/{box['id']}", json={"discharged_at": "2026-03-10T08:00:00Z"})
    loads = [{"po_line_id": ln["id"], "quantity": "10"} for ln in po["lines"]]
    client.put(f"/api/v1/containers/{box['id']}/loads", json=loads)
    cost(client, box["id"], "CUSTOMS_DUTY", "50.00", allocation_method="BY_CIF_VALUE")
    cost(client, box["id"], "OCEAN_FREIGHT", "100.00", allocation_method="BY_WEIGHT")  # no weights anywhere
    codes = {f["code"]: f for f in audit(client)["findings"]}
    assert codes["DUTY_RATE_MISSING"]["params"]["lines"] == "1"
    assert (codes["UNALLOCATED_COST"]["amount"], codes["UNALLOCATED_COST"]["params"]["reason"]) == (
        "100.00",
        "MISSING_BASIS",
    )


# ------------------------------------------------------------------------------- the other sections


def test_the_first_page_is_the_sum_of_its_sections_and_the_sections_are_the_reports(
    client: TestClient,
) -> None:
    client.post("/api/v1/organization/sample-data", params={"profile": "history"})
    client.post("/api/v1/products", json={"sku": "TYR-20555R16-91V", "sale_price": "39.90"})
    client.patch("/api/v1/organization", json={"settings": {"assumed_coefficient": "1.10"}})
    today = datetime.now(UTC).date()
    period = {"period_from": (today - timedelta(days=90)).isoformat(), "period_to": today.isoformat()}
    body = audit(client, **period)

    head = body["headline"]
    priced = [m for m in body["margins"] if m["sale_price"] is not None]
    assert head["priced_skus"] == 1 and head["unpriced_skus"] == len(body["margins"]) - 1
    assert Decimal(head["margin_overstated"]) == sum(Decimal(m["approach_costs"]) for m in priced)
    claim = [
        f for f in body["findings"] if f["code"] in ("DUPLICATE_CHARGE", "ABOVE_QUOTE", "OUTLIER_CHARGE")
    ]
    assert Decimal(head["recoverable_sure"]) == sum(
        Decimal(f["amount"]) for f in claim if f["confidence"] == "sure"
    )
    assert Decimal(head["recoverable_to_check"]) == sum(
        Decimal(f["amount"]) for f in claim if f["confidence"] == "to_check"
    )
    assert Decimal(head["demurrage_paid"]) == sum(Decimal(d["paid"]) for d in body["demurrage"])

    tyre = priced[0]
    assert tyre["points_lost"] == str(Decimal(tyre["margin_on_fob_pct"]) - Decimal(tyre["margin_real_pct"]))
    assert body["assumed_coefficient"] == "1.1000" and Decimal(body["coefficient"]) > 1
    monthly = client.get("/api/v1/reports/landed-cost", params={"group_by": "month", **period}).json()
    assert [b["key"] for b in body["coefficient_by_month"]] == [b["key"] for b in monthly["buckets"]]
    assert [b["landed"] for b in body["coefficient_by_month"]] == [b["landed"] for b in monthly["buckets"]]
    dnd = client.get("/api/v1/reports/dnd", params=period).json()
    assert [d["paid"] for d in body["demurrage"]] == [ln["paid"] for ln in dnd["lines"]]
    assert body["completeness"]["containers"] > 0 and "ecb" in body["completeness"]["fx_sources"]


def test_the_six_month_dataset_carries_the_three_flaws_that_were_put_in_it_and_nothing_untrue(
    client: TestClient,
) -> None:
    client.post("/api/v1/organization/sample-data", params={"profile": "history"})
    today = datetime.now(UTC).date()
    period = {"period_from": (today - timedelta(days=200)).isoformat(), "period_to": today.isoformat()}
    body = audit(client, **period)
    by_code: dict[str, list[dict[str, Any]]] = {}
    for f in body["findings"]:
        by_code.setdefault(f["code"], []).append(f)
    assert set(by_code) == {
        "DUPLICATE_CHARGE", "OUTLIER_CHARGE", "ESTIMATE_NEVER_INVOICED", "DUTY_RATE_MISSING", "ABOVE_QUOTE"
    }  # fmt: skip

    (duplicate,) = by_code["DUPLICATE_CHARGE"]
    assert (duplicate["cost_type"], duplicate["amount"], duplicate["confidence"]) == ("THC", "255.00", "sure")
    assert duplicate["invoice_number"].startswith("TH-2026-") and len(duplicate["cost_ids"]) == 2
    (outlier,) = by_code["OUTLIER_CHARGE"]
    assert (outlier["cost_type"], outlier["confidence"], outlier["vendor"]) == (
        "DRAYAGE",
        "to_check",
        "TRANSPORTS LEMAIRE",
    )
    assert outlier["basis"] >= 4 and Decimal(outlier["params"]["ratio"]) >= 3
    (forgotten,) = by_code["ESTIMATE_NEVER_INVOICED"]
    assert forgotten["cost_type"] == "CUSTOMS_BROKERAGE" and int(forgotten["params"]["days"]) >= 60
    (no_rate,) = by_code["DUTY_RATE_MISSING"]
    assert no_rate["cost_type"] == "CUSTOMS_DUTY" and no_rate["params"]["lines"] == "1"
    assert VOYAGES[DUPLICATE_THC_ON].fate == "closed" and VOYAGES[OUTLIER_DRAYAGE_ON].fate == "closed"
    assert VOYAGES[NEVER_INVOICED_ON].arrived_days_ago >= 60

    # the invoices above their quotes are the dataset's ordinary surcharges: each one is an invoice
    # that replaced a quote, the excess is the difference, and none is under 5 % or 50 euros
    for above in by_code["ABOVE_QUOTE"]:
        actual = client.get(f"/api/v1/costs/{above['cost_ids'][0]}").json()
        quote = client.get(f"/api/v1/costs/{actual['supersedes_cost_id']}").json()
        assert Decimal(above["amount"]) == Decimal(actual["amount_base"]) - Decimal(quote["amount_base"])
        assert Decimal(above["amount"]) >= 50 and Decimal(above["params"]["share_pct"]) >= 5
    surprised = [c for c in client.get("/api/v1/costs").json() if c["supersedes_cost_id"]]
    assert 0 < len(by_code["ABOVE_QUOTE"]) < len(surprised)  # the small ones are left alone


def test_an_audit_can_be_sent_by_link_and_stays_what_it_was(client: TestClient) -> None:
    client.post("/api/v1/organization/sample-data", params={"profile": "history"})
    today = datetime.now(UTC).date()
    period = {"period_from": (today - timedelta(days=200)).isoformat(), "period_to": today.isoformat()}
    created = client.post("/api/v1/reports/audit/share", json={**period, "redact_vendors": True})
    assert created.status_code == 201, created.text
    before = audit(client, **period)
    assert created.json()["landed"] == before["completeness"]["landed"]

    box = client.get("/api/v1/containers").json()[0]["id"]
    cost(client, box, "INSPECTION", "145.00", cost_date=today.isoformat())
    opened = client.post(
        "/api/v1/public/shared-reports/open",
        json={"token": created.json()["token"]},
        headers={"X-Org-Id": ""},
    )
    assert opened.status_code == 200, opened.text
    public = opened.json()
    assert (public["subject_type"], public["report"], public["redacted"]) == ("audit", None, True)
    assert public["audit"]["headline"] == before["headline"]
    assert all(f["vendor"] is None and f["invoice_number"] is None for f in public["audit"]["findings"])
    assert "TRANSITEX" not in opened.text
    (listed,) = client.get("/api/v1/reports/audit/shares").json()
    assert (listed["subject_type"], listed["view_count"]) == ("audit", 1)


def test_the_findings_are_a_file_in_french(client: TestClient) -> None:
    box = landed(client, "MSCU4821990", "2026-03-10")
    cost(client, box, "THC", "262.00", vendor="TRANSITEX SAS", invoice_number="FA-1")
    cost(client, box, "THC", "260.00", vendor="TERMINAL", invoice_number="TH-9")
    res = client.get("/api/v1/exports/audit-findings.csv", params=PERIOD)
    assert res.status_code == 200
    head, row = res.text.lstrip("﻿").splitlines()[:2]
    assert head.startswith("Constat;Certitude;Montant en devise de base;N° conteneur;Type de coût")
    assert row.startswith(
        "Prestation facturée deux fois;Établi;260,00;MSCU4821990;Manutention portuaire (THC)"
    )


@pytest.mark.parametrize("bad", [{"period_from": "2026-04-01", "period_to": "2026-03-01"}])
def test_a_period_that_ends_before_it_starts_is_refused(client: TestClient, bad: dict[str, str]) -> None:
    assert client.get("/api/v1/reports/audit", params=bad).json()["code"] == "PERIOD_INVALID"
    assert client.post("/api/v1/reports/audit/share", json=bad).json()["code"] == "PERIOD_INVALID"


def test_the_assumed_coefficient_is_a_ratio_not_a_percentage(client: TestClient) -> None:
    res = client.patch("/api/v1/organization", json={"settings": {"assumed_coefficient": 15}})
    assert res.status_code == 422 and res.json()["code"] == "ASSUMED_COEFFICIENT_INVALID"
    assert (
        client.patch("/api/v1/organization", json={"settings": {"assumed_coefficient": "1.15"}}).status_code
        == 200
    )
