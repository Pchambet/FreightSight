"""Decode and tabulate an uploaded CSV/XLSX; suggest a column mapping. Pure functions."""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from charset_normalizer import from_bytes

from app.domain.models import ImportKind

CONTAINER_NUMBER_RE = re.compile(r"^[A-Z]{4}[0-9]{7}$")

# Target field -> accepted header spellings (normalised: lowercase, no accents, spaces -> _)
TARGET_ALIASES: dict[ImportKind, dict[str, list[str]]] = {
    ImportKind.PURCHASE_ORDERS: {
        "po_number": [
            "po_number",
            "po",
            "n_commande",
            "numero_commande",
            "commande",
            "order",
            "order_number",
        ],
        "supplier_name": ["supplier_name", "supplier", "fournisseur", "vendor"],
        "currency": ["currency", "devise", "cur"],
        "order_date": ["order_date", "date", "date_commande"],
        "incoterm": ["incoterm"],
        "line_no": ["line_no", "line", "ligne", "n_ligne", "pos"],
        "sku": ["sku", "reference", "ref", "article", "item", "product", "code"],
        "description": ["description", "designation", "libelle", "label"],
        "quantity": ["quantity", "qty", "qte", "quantite"],
        "unit_price": ["unit_price", "price", "prix", "prix_unitaire", "pu"],
        "unit_weight_kg": ["unit_weight_kg", "weight_kg", "weight", "poids", "poids_kg", "kg"],
        "unit_volume_cbm": ["unit_volume_cbm", "volume_cbm", "volume", "cbm", "m3"],
        "hs_code": ["hs_code", "hs", "nc", "code_nc", "taric", "tariff"],
        "duty_rate": ["duty_rate", "duty", "droits", "taux_droits"],
        "container_number": ["container_number", "container", "conteneur", "ctn", "box"],
        "container_quantity": ["container_quantity", "qty_in_container", "qte_conteneur", "loaded_qty"],
    },
    ImportKind.LEGACY_PO_CONTAINER: {
        "po_number": ["po_number", "po", "n_commande", "numero_commande", "commande"],
        "supplier_name": ["supplier_name", "supplier", "fournisseur"],
        "total_value": ["total_value", "value", "montant", "valeur", "total"],
        "container_number": ["container_number", "container", "conteneur"],
        "allocation_percentage": ["allocation_percentage", "allocation_pct", "allocation"],
    },
}

REQUIRED: dict[ImportKind, list[str]] = {
    ImportKind.PURCHASE_ORDERS: ["po_number", "quantity", "unit_price"],
    ImportKind.LEGACY_PO_CONTAINER: ["po_number"],
}


class ImportError_(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Table:
    columns: list[str]  # original headers, stripped
    rows: list[dict[str, str]]  # header -> raw cell, keyed by original header
    encoding: str
    delimiter: str


def decode_bytes(content: bytes) -> tuple[str, str]:
    try:
        return content.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        pass
    best = from_bytes(content).best()
    if best is None:
        raise ImportError_("ENCODING_UNKNOWN", "Could not detect the file encoding.")
    return str(best), best.encoding


def sniff_delimiter(text: str) -> str:
    sample = text[:8192]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
    except csv.Error:
        return ";" if sample.count(";") > sample.count(",") else ","


def normalize_header(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = s.strip().strip('"').casefold()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


def parse_table(content: bytes, filename: str | None = None) -> Table:
    if filename and filename.lower().endswith((".xlsx", ".xlsm")):
        return _parse_xlsx(content)
    text, encoding = decode_bytes(content)
    delimiter = sniff_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        header = [h.strip() for h in next(reader)]
    except StopIteration as e:
        raise ImportError_("EMPTY_FILE", "The file has no header row.") from e
    rows = []
    for values in reader:
        if not any(v.strip() for v in values):
            continue
        rows.append({header[i]: values[i].strip() for i in range(min(len(header), len(values)))})
    return Table(columns=header, rows=rows, encoding=encoding, delimiter=delimiter)


def _parse_xlsx(content: bytes) -> Table:
    try:
        import openpyxl
    except ImportError as e:  # pragma: no cover
        raise ImportError_("XLSX_UNSUPPORTED", "XLSX support is not installed.") from e
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.worksheets[0]
    it = ws.iter_rows(values_only=True)
    try:
        header = [str(h).strip() if h is not None else "" for h in next(it)]
    except StopIteration as e:
        raise ImportError_("EMPTY_FILE", "The sheet has no header row.") from e
    rows = []
    for values in it:
        cells = ["" if v is None else str(v).strip() for v in values]
        if not any(cells):
            continue
        rows.append({header[i]: cells[i] for i in range(min(len(header), len(cells))) if header[i]})
    return Table(columns=[h for h in header if h], rows=rows, encoding="xlsx", delimiter="")


def suggest_mapping(kind: ImportKind, columns: list[str]) -> dict[str, str]:
    """target field -> source column, by alias match."""
    normalised = {normalize_header(c): c for c in columns}
    mapping: dict[str, str] = {}
    for target, aliases in TARGET_ALIASES[kind].items():
        for alias in aliases:
            if alias in normalised and normalised[alias] not in mapping.values():
                mapping[target] = normalised[alias]
                break
    return mapping


def header_signature(columns: list[str]) -> str:
    return "|".join(sorted(normalize_header(c) for c in columns))


def parse_decimal(raw: str | None) -> Decimal | None:
    """Accepts '12500.50', '12 500,50', '12.500,50', '12,500.50', '4,5 %'. Blank -> None."""
    if raw is None:
        return None
    s = raw.strip().replace(" ", "").replace("\u00a0", "").replace("\u202f", "").replace("%", "")
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        head, _, tail = s.rpartition(",")
        s = f"{head}.{tail}" if len(tail) in (1, 2) else s.replace(",", "")
    try:
        return Decimal(s)
    except InvalidOperation as e:
        raise ImportError_("NOT_A_NUMBER", f"{raw!r} is not a number") from e
