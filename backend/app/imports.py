"""CSV decoding and row parsing for purchase-order imports.

Handles what real exports look like: Excel's UTF-8 BOM, Sage/EBP cp1252, `;` delimiters, `12 500,50` numbers.
Pure functions; the router does the database work.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from charset_normalizer import from_bytes

_HEADER_ALIASES: dict[str, str] = {
    "po_number": "po_number",
    "po": "po_number",
    "n° commande": "po_number",
    "numero commande": "po_number",
    "commande": "po_number",
    "supplier_name": "supplier_name",
    "supplier": "supplier_name",
    "fournisseur": "supplier_name",
    "total_value": "total_value",
    "value": "total_value",
    "montant": "total_value",
    "valeur": "total_value",
    "container_number": "container_number",
    "container": "container_number",
    "conteneur": "container_number",
    "allocation_percentage": "allocation_percentage",
    "allocation_pct": "allocation_percentage",
    "allocation": "allocation_percentage",
}

CONTAINER_NUMBER_RE = re.compile(r"^[A-Z]{4}[0-9]{7}$")


class ImportError_(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def decode_bytes(content: bytes) -> str:
    """UTF-8 (with or without BOM) first, then charset detection for cp1252/latin-1 exports."""
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    best = from_bytes(content).best()
    if best is None:
        raise ImportError_("ENCODING_UNKNOWN", "Could not detect the file encoding.")
    return str(best)


def sniff_delimiter(text: str) -> str:
    sample = text[:8192]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
    except csv.Error:
        return ";" if sample.count(";") > sample.count(",") else ","


def normalize_header(name: str) -> str:
    key = name.strip().strip('"').casefold().replace("_", " ")
    key = re.sub(r"\s+", " ", key)
    return _HEADER_ALIASES.get(key, _HEADER_ALIASES.get(key.replace(" ", "_"), key.replace(" ", "_")))


def parse_decimal(raw: str | None) -> Decimal | None:
    """Accepts '12500.50', '12 500,50', '12.500,50', '12,500.50'. Returns None for blank."""
    if raw is None:
        return None
    s = raw.strip().replace("\u00a0", "").replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:
        # whichever comes last is the decimal separator
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        # a single comma: decimal separator if followed by 1-2 digits, else thousands separator
        head, _, tail = s.rpartition(",")
        s = f"{head}.{tail}" if len(tail) in (1, 2) else s.replace(",", "")
    try:
        return Decimal(s)
    except InvalidOperation as e:
        raise ImportError_("NOT_A_NUMBER", f"{raw!r} is not a number") from e


@dataclass(frozen=True)
class PoRow:
    row_no: int
    po_number: str
    supplier_name: str | None
    total_value: Decimal
    container_number: str | None
    allocation_percentage: Decimal | None


@dataclass(frozen=True)
class RowError:
    row_no: int
    code: str
    message: str


def parse_po_csv(content: bytes) -> tuple[list[PoRow], list[RowError], list[str]]:
    """Returns (rows, row_errors, detected_columns). Header errors raise ImportError_."""
    text = decode_bytes(content)
    delimiter = sniff_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        raw_header = next(reader)
    except StopIteration as e:
        raise ImportError_("EMPTY_FILE", "The file has no header row.") from e
    header = [normalize_header(h) for h in raw_header]
    if "po_number" not in header:
        raise ImportError_(
            "MISSING_COLUMN", f"No 'po_number' column found. Detected columns: {', '.join(header)}"
        )

    rows: list[PoRow] = []
    errors: list[RowError] = []
    for row_no, values in enumerate(reader, start=2):
        if not any(v.strip() for v in values):
            continue
        record = {header[i]: values[i].strip() for i in range(min(len(header), len(values)))}
        po_number = record.get("po_number", "")
        if not po_number:
            errors.append(RowError(row_no, "REQUIRED", "po_number is empty"))
            continue
        try:
            total_value = parse_decimal(record.get("total_value")) or Decimal("0")
            pct = parse_decimal(record.get("allocation_percentage"))
        except ImportError_ as e:
            errors.append(RowError(row_no, e.code, e.message))
            continue
        container_number = (record.get("container_number") or "").upper() or None
        if container_number and not CONTAINER_NUMBER_RE.match(container_number):
            errors.append(
                RowError(
                    row_no, "INVALID_CONTAINER_NUMBER", f"{container_number!r} is not an ISO 6346 number"
                )
            )
            continue
        rows.append(
            PoRow(
                row_no=row_no,
                po_number=po_number,
                supplier_name=record.get("supplier_name") or None,
                total_value=total_value,
                container_number=container_number,
                allocation_percentage=pct,
            )
        )
    return rows, errors, header
