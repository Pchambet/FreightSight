from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

FIXTURES = Path(__file__).parent / "fixtures"

PO_LINES_CSV = (
    "﻿N° commande;Fournisseur;Réf;Qté;Prix unitaire;Poids;Volume;Conteneur;Qté conteneur\n"
    "PO-A;Michelin;A;1000;10,00;2;0,01;MSCU1234567;600\n"
    "PO-A;Michelin;A;1000;10,00;2;0,01;CMAU9876543;400\n"
    "PO-B;Pirelli;B;500;20,00;5;0,02;MSCU1234567;500\n"
    "PO-C;Hankook;C;10;abc;;;;\n"
).encode()


def upload(client: TestClient, content: bytes, kind: str, name: str = "file.csv") -> dict[str, Any]:
    res = client.post("/api/v1/imports", data={"kind": kind}, files={"file": (name, content, "text/csv")})
    assert res.status_code == 201, res.text
    return dict(res.json())


def test_legacy_import_validate_then_commit(client: TestClient) -> None:
    job = upload(client, (FIXTURES / "legacy_po_container.csv").read_bytes(), "LEGACY_PO_CONTAINER")
    assert job["status"] == "PARSED" and job["row_count"] == 3
    assert job["mapping"]["po_number"] == "po_number"

    res = client.post(f"/api/v1/imports/{job['id']}/validate", json={"mapping": job["mapping"]})
    assert res.status_code == 200, res.text
    report = res.json()["report"]
    assert res.json()["status"] == "VALIDATED"
    assert report["valid_rows"] == 3 and report["errors"] == []
    assert (
        report["purchase_orders_created"] == 3
        and report["containers_created"] == 2
        and report["loads_created"] == 3
    )
    assert [w["code"] for w in report["warnings"]] == ["DEPRECATED_COLUMN"]
    # dry run wrote nothing
    assert client.get("/api/v1/containers").json() == []

    res = client.post(f"/api/v1/imports/{job['id']}/commit", json={})
    assert res.status_code == 200 and res.json()["status"] == "DONE"
    containers = {c["container_number"]: c for c in client.get("/api/v1/containers").json()}
    assert set(containers) == {"MSCU1234567", "CMAU9876543"}
    assert containers["MSCU1234567"]["fob_base"] == "20900.50"

    # a second commit is refused; a re-upload of the same file is a no-op
    assert client.post(f"/api/v1/imports/{job['id']}/commit", json={}).status_code == 409
    job2 = upload(client, (FIXTURES / "legacy_po_container.csv").read_bytes(), "LEGACY_PO_CONTAINER")
    res = client.post(f"/api/v1/imports/{job2['id']}/commit", json={})
    assert res.json()["report"]["purchase_orders_created"] == 0
    assert res.json()["report"]["loads_created"] == 0


def test_po_lines_import_with_mapping_and_row_errors(client: TestClient) -> None:
    job = upload(client, PO_LINES_CSV, "PURCHASE_ORDERS", "export_excel.csv")
    assert job["encoding"] == "utf-8" and job["delimiter"] == ";"
    mapping = job["mapping"]
    assert mapping["po_number"] == "N° commande" and mapping["container_quantity"] == "Qté conteneur"

    res = client.post(f"/api/v1/imports/{job['id']}/validate", json={"mapping": mapping})
    report = res.json()["report"]
    assert report["valid_rows"] == 3
    assert [(e["row"], e["field"], e["code"]) for e in report["errors"]] == [
        (5, "unit_price", "NOT_A_NUMBER")
    ]
    assert (
        report["purchase_orders_created"] == 2
        and report["lines_created"] == 2
        and report["loads_created"] == 3
    )

    res = client.post(f"/api/v1/imports/{job['id']}/commit", json={"on_error": "abort"})
    assert res.status_code == 422 and res.json()["code"] == "IMPORT_ABORTED"
    res = client.post(f"/api/v1/imports/{job['id']}/commit", json={"on_error": "skip_rows"})
    assert res.status_code == 200, res.text

    pos = {p["po_number"]: p for p in client.get("/api/v1/purchase-orders").json()}
    assert set(pos) == {"PO-A", "PO-B"}
    assert pos["PO-A"]["container_numbers"] == ["CMAU9876543", "MSCU1234567"]
    assert pos["PO-A"]["supplier_name"] == "Michelin"

    # the mapping is remembered for the same header
    job3 = upload(client, PO_LINES_CSV, "PURCHASE_ORDERS")
    assert job3["mapping"] == mapping


def test_mapping_missing_required_field(client: TestClient) -> None:
    job = upload(client, b"xyz,qty,price\nPO-1,1,2\n", "PURCHASE_ORDERS")
    assert job["mapping"] == {"quantity": "qty", "unit_price": "price"}
    res = client.post(f"/api/v1/imports/{job['id']}/validate", json={"mapping": job["mapping"]})
    assert res.status_code == 422 and res.json()["code"] == "MAPPING_INCOMPLETE"
    res = client.post(
        f"/api/v1/imports/{job['id']}/validate", json={"mapping": {**job["mapping"], "po_number": "xyz"}}
    )
    assert res.status_code == 200 and res.json()["report"]["valid_rows"] == 1


def test_no_valid_rows_is_422(client: TestClient) -> None:
    job = upload(client, b"po_number,quantity,unit_price\n,1,2\n,3,4\n", "PURCHASE_ORDERS")
    res = client.post(f"/api/v1/imports/{job['id']}/validate", json={"mapping": job["mapping"]})
    assert res.status_code == 422 and res.json()["code"] == "NO_VALID_ROWS"
    assert len(res.json()["report"]["errors"]) == 2


def test_over_allocation_in_file_is_a_row_error(client: TestClient) -> None:
    content = (
        b"po_number,quantity,unit_price,container_number,container_quantity\n"
        b"PO-1,100,1,MSCU1234567,80\n"
        b"PO-1,100,1,CMAU9876543,30\n"
    )
    job = upload(client, content, "PURCHASE_ORDERS")
    res = client.post(f"/api/v1/imports/{job['id']}/validate", json={"mapping": job["mapping"]})
    report = res.json()["report"]
    assert report["valid_rows"] == 1
    assert report["errors"][0]["code"] == "OVER_ALLOCATED" and report["errors"][0]["row"] == 3


def test_a_reimport_without_a_column_keeps_what_was_typed_by_hand(client: TestClient) -> None:
    """Weights, volumes, HS codes and duty rates are enrichment: a file (or an ERP) that does not
    carry them must not blank them, or the freight split by weight silently collapses at the next
    sync. What the order itself says still follows the source."""
    first = b"po_number;sku;quantity;unit_price;unit_weight_kg;duty_rate\nPO-W;W;100;10,00;2,5;0,045\n"
    job = upload(client, first, "PURCHASE_ORDERS", "with_weights.csv")
    res = client.post(
        f"/api/v1/imports/{job['id']}/commit", json={"mapping": job["mapping"], "on_error": "abort"}
    )
    assert res.status_code == 200, res.text

    second = b"po_number;sku;quantity;unit_price\nPO-W;W;120;11,00\n"
    job2 = upload(client, second, "PURCHASE_ORDERS", "without_weights.csv")
    res = client.post(
        f"/api/v1/imports/{job2['id']}/commit", json={"mapping": job2["mapping"], "on_error": "abort"}
    )
    assert res.status_code == 200, res.text

    (po,) = [p for p in client.get("/api/v1/purchase-orders").json() if p["po_number"] == "PO-W"]
    (line,) = client.get(f"/api/v1/purchase-orders/{po['id']}").json()["lines"]
    assert line["quantity"].startswith("120") and line["unit_price"].startswith("11")
    assert line["unit_weight_kg"].startswith("2.5") and line["duty_rate"].startswith("0.045")

    # a value in the file still wins over the old one
    third = b"po_number;sku;quantity;unit_price;unit_weight_kg\nPO-W;W;120;11,00;3\n"
    job3 = upload(client, third, "PURCHASE_ORDERS", "new_weight.csv")
    assert (
        client.post(
            f"/api/v1/imports/{job3['id']}/commit", json={"mapping": job3["mapping"], "on_error": "abort"}
        ).status_code
        == 200
    )
    (line,) = client.get(f"/api/v1/purchase-orders/{po['id']}").json()["lines"]
    assert line["unit_weight_kg"].startswith("3")


def test_a_comma_after_a_lone_zero_is_a_decimal_point() -> None:
    """French files put three decimals on rates and volumes. "0,045" is four and a half percent,
    not forty-five; "0,012" is twelve litres, not twelve cubic metres. The genuinely ambiguous
    "12,500" stays the English twelve thousand five hundred, and two commas are thousands."""
    from decimal import Decimal

    from app.domain.imports.parsing import parse_decimal

    assert parse_decimal("0,045") == Decimal("0.045")
    assert parse_decimal("-0,125") == Decimal("-0.125")
    assert parse_decimal(",5") == Decimal("0.5")
    assert parse_decimal("12,500") == Decimal("12500")
    assert parse_decimal("1,234,567") == Decimal("1234567")
    assert parse_decimal("12 500,50") == Decimal("12500.50")
    assert parse_decimal("12.500,50") == Decimal("12500.50")
    assert parse_decimal("4,5 %") == Decimal("4.5")
