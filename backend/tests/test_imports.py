from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.imports import ImportError_, parse_decimal, parse_po_csv

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_decimal_accepts_french_and_english_formats() -> None:
    assert parse_decimal("12500.50") == Decimal("12500.50")
    assert parse_decimal("12 500,50") == Decimal("12500.50")
    assert parse_decimal("12.500,50") == Decimal("12500.50")
    assert parse_decimal("12,500.50") == Decimal("12500.50")
    assert parse_decimal("1,500") == Decimal("1500")
    assert parse_decimal("1,5") == Decimal("1.5")
    assert parse_decimal("") is None
    with pytest.raises(ImportError_):
        parse_decimal("12,5 pcs")


def test_legacy_fixture_parses() -> None:
    rows, errors, columns = parse_po_csv((FIXTURES / "legacy_po_container.csv").read_bytes())
    assert errors == []
    assert columns == [
        "po_number",
        "supplier_name",
        "total_value",
        "container_number",
        "allocation_percentage",
    ]
    assert [r.po_number for r in rows] == ["PO-2026-001", "PO-2026-002", "PO-2026-003"]
    assert rows[0].total_value == Decimal("12500.50")
    assert rows[1].allocation_percentage == Decimal("50")


def test_excel_fr_export_with_bom_and_semicolon() -> None:
    """Excel FR: UTF-8 BOM, ';' delimiter, comma decimals, French headers."""
    content = (
        "\ufeffN° commande;Fournisseur;Montant;Conteneur\nPO-1;Société Générale Pneus;12 500,50;MSCU1234567\n"
    ).encode()
    rows, errors, columns = parse_po_csv(content)
    assert errors == []
    assert columns == ["po_number", "supplier_name", "total_value", "container_number"]
    assert rows[0].supplier_name == "Société Générale Pneus"
    assert rows[0].total_value == Decimal("12500.50")
    assert rows[0].container_number == "MSCU1234567"


def test_latin1_export_decodes() -> None:
    content = "po_number,supplier_name,total_value\nPO-1,Société Générale,100\n".encode("cp1252")
    rows, errors, _ = parse_po_csv(content)
    assert errors == []
    assert rows[0].supplier_name == "Société Générale"


def test_row_errors_are_reported_not_fatal() -> None:
    content = (
        b"po_number,total_value,container_number\n"
        b"PO-1,100,MSCU1234567\n"
        b",100,MSCU1234567\n"
        b"PO-3,abc,MSCU1234567\n"
        b"PO-4,100,NOT-A-BOX\n"
        b"\n"
    )
    rows, errors, _ = parse_po_csv(content)
    assert [r.po_number for r in rows] == ["PO-1"]
    assert [(e.row_no, e.code) for e in errors] == [
        (3, "REQUIRED"),
        (4, "NOT_A_NUMBER"),
        (5, "INVALID_CONTAINER_NUMBER"),
    ]


def test_missing_po_number_column_is_an_import_error() -> None:
    with pytest.raises(ImportError_) as exc:
        parse_po_csv(b"order,value\nPO-1,10\n")
    assert exc.value.code == "MISSING_COLUMN"
