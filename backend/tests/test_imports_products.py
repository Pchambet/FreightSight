"""Reading a tariff: articles written on their reference, a cell left empty saying nothing, and the
order lines already written keeping what they said — which is why the tariff is loaded first."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient

HEADER = (
    "Référence;Désignation;Code SH;Taux de droits;Poids unitaire (kg);Volume unitaire (m³);"
    "Prix de vente HT;Devise de vente"
)


def tariff(*rows: str) -> bytes:
    return ("﻿" + "\n".join([HEADER, *rows]) + "\n").encode()


def imported(client: TestClient, content: bytes) -> dict[str, Any]:
    job = client.post(
        "/api/v1/imports", data={"kind": "PRODUCTS"}, files={"file": ("tarif.csv", content, "text/csv")}
    ).json()
    previewed = client.post(f"/api/v1/imports/{job['id']}/validate", json={"mapping": job["mapping"]})
    if previewed.status_code == 422:
        report: dict[str, Any] = previewed.json()["report"]
        return report
    assert previewed.status_code == 200, previewed.text
    committed = client.post(f"/api/v1/imports/{job['id']}/commit", json={})
    assert committed.status_code == 200, committed.text
    report = committed.json()["report"]
    return report


def products(client: TestClient) -> dict[str, dict[str, Any]]:
    return {p["sku"]: p for p in client.get("/api/v1/products").json()["products"]}


def test_a_tariff_writes_its_articles_and_saying_the_same_again_changes_nothing(client: TestClient) -> None:
    rows = ("TYRE;Pneu 205/55R16;40111000;4,5;9,5;0,05;60,00;EUR",
            "JACK;Cric hydraulique;84254200;0;4;0,01;35,00;EUR")  # fmt: skip
    report = imported(client, tariff(*rows))
    assert (report["products_created"], report["products_updated"], report["errors"]) == (2, 0, [])
    tyre = products(client)["TYRE"]
    assert (tyre["duty_rate"], tyre["hs_code"], tyre["sale_price"], tyre["sale_currency"]) == (
        "0.045",  # « 4,5 » is a per cent
        "40111000",
        "60.0000",
        "EUR",
    )
    again = imported(client, tariff(*rows))
    assert (again["products_created"], again["products_updated"]) == (0, 0)


def test_an_empty_cell_says_nothing_and_a_price_without_currency_says_so(client: TestClient) -> None:
    imported(client, tariff("TYRE;Pneu;40111000;4,5;9,5;0,05;60,00;EUR"))
    report = imported(client, tariff("TYRE;;;;;;62,00;"))
    assert report["products_updated"] == 1
    assert [w["code"] for w in report["warnings"]] == ["SALE_CURRENCY_ASSUMED"]
    tyre = products(client)["TYRE"]
    assert (tyre["description"], tyre["duty_rate"], tyre["sale_price"]) == ("Pneu", "0.045", "62.0000")


def test_order_lines_already_written_keep_what_they_said_and_new_ones_borrow_from_the_tariff(
    client: TestClient,
) -> None:
    body = {"po_number": "PO-1", "currency": "EUR", "lines": [{"line_no": 1, "sku": "TYRE", "quantity": "10",
            "unit_price": "14"}]}  # fmt: skip
    before = client.post("/api/v1/purchase-orders", json=body).json()
    imported(client, tariff("TYRE;Pneu;40111000;4,5;9,5;0,05;60,00;EUR"))
    after = client.post("/api/v1/purchase-orders", json={**body, "po_number": "PO-2"}).json()
    rates = {
        po["po_number"]: client.get(f"/api/v1/purchase-orders/{po['id']}").json()["lines"][0]["duty_rate"]
        for po in (before, after)
    }
    assert {po: rate and Decimal(rate) for po, rate in rates.items()} == {
        "PO-1": None,
        "PO-2": Decimal("0.045"),
    }


def test_what_a_tariff_cannot_say_is_refused_by_name(client: TestClient) -> None:
    report = imported(client, tariff("TYRE;Pneu;;-1;;;;", "TYRE;Pneu bis;;;;;;", ";Sans référence;;;;;;",
                                     "MAT;Tapis;;;;;10;EURO"))  # fmt: skip
    assert {issue["row"]: issue["code"] for issue in report["errors"]} == {
        2: "NEGATIVE",
        4: "REQUIRED",
        5: "INVALID_CURRENCY",
    }
    assert report["products_created"] == 1  # the second TYRE row, the first having been refused
