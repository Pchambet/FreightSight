from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.imports.parsing import (
    ImportError_,
    header_signature,
    normalize_header,
    parse_decimal,
    parse_table,
    suggest_mapping,
)
from app.domain.models import ImportKind

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_decimal_formats() -> None:
    assert parse_decimal("12500.50") == Decimal("12500.50")
    assert parse_decimal("12 500,50") == Decimal("12500.50")
    assert parse_decimal("12.500,50") == Decimal("12500.50")
    assert parse_decimal("12,500.50") == Decimal("12500.50")
    assert parse_decimal("1,500") == Decimal("1500")
    assert parse_decimal("4,5 %") == Decimal("4.5")
    assert parse_decimal("") is None
    with pytest.raises(ImportError_):
        parse_decimal("12,5 pcs")


def test_normalize_header_strips_accents_and_punctuation() -> None:
    assert normalize_header("N° commande") == "n_commande"
    assert normalize_header(" Qté ") == "qte"
    assert normalize_header("Prix unitaire (EUR)") == "prix_unitaire_eur"


def test_legacy_fixture_and_mapping() -> None:
    table = parse_table((FIXTURES / "legacy_po_container.csv").read_bytes())
    assert table.columns == [
        "po_number",
        "supplier_name",
        "total_value",
        "container_number",
        "allocation_percentage",
    ]
    assert len(table.rows) == 3
    mapping = suggest_mapping(ImportKind.LEGACY_PO_CONTAINER, table.columns)
    assert mapping == {c: c for c in table.columns}


def test_excel_fr_bom_semicolon_and_aliases() -> None:
    content = (
        "﻿N° commande;Fournisseur;Réf;Qté;Prix unitaire;Poids;Conteneur\n"
        "PO-1;Société Générale Pneus;TYRE-205;600;12,50;2,1;MSCU1234567\n"
    ).encode()
    table = parse_table(content)
    assert table.delimiter == ";" and table.encoding == "utf-8"
    mapping = suggest_mapping(ImportKind.PURCHASE_ORDERS, table.columns)
    assert mapping == {
        "po_number": "N° commande",
        "supplier_name": "Fournisseur",
        "sku": "Réf",
        "quantity": "Qté",
        "unit_price": "Prix unitaire",
        "unit_weight_kg": "Poids",
        "container_number": "Conteneur",
    }
    assert table.rows[0]["Fournisseur"] == "Société Générale Pneus"


def test_cp1252_export_decodes() -> None:
    table = parse_table("po_number,supplier,qty,price\nPO-1,Société Générale,1,100\n".encode("cp1252"))
    assert table.rows[0]["supplier"] == "Société Générale"
    assert table.encoding.lower() in ("cp1252", "windows-1252", "latin_1", "iso8859_1", "cp1250", "cp1254")


def test_header_signature_is_order_independent() -> None:
    assert header_signature(["B", "a"]) == header_signature(["A", "b"])


def test_missing_header_row() -> None:
    with pytest.raises(ImportError_) as exc:
        parse_table(b"")
    assert exc.value.code == "EMPTY_FILE"
