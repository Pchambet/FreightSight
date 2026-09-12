"""Import jobs: parse → validate (dry run under a SAVEPOINT) → commit. Same code path both times."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from app.core.errors import Conflict, Unprocessable
from app.core.tenancy import TenantSession
from app.domain.costing.service import recompute_org
from app.domain.imports.parsing import (
    CONTAINER_NUMBER_RE,
    REQUIRED,
    ImportError_,
    Table,
    header_signature,
    parse_decimal,
    parse_table,
    suggest_mapping,
)
from app.domain.models import (
    Container,
    ContainerLoad,
    ImportJob,
    ImportKind,
    ImportMapping,
    ImportStatus,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
)


@dataclass
class RowIssue:
    row: int
    field: str
    code: str
    message: str


@dataclass
class ImportReport:
    row_count: int = 0
    valid_rows: int = 0
    errors: list[RowIssue] = field(default_factory=list)
    warnings: list[RowIssue] = field(default_factory=list)
    purchase_orders_created: int = 0
    purchase_orders_updated: int = 0
    lines_created: int = 0
    lines_updated: int = 0
    containers_created: int = 0
    loads_created: int = 0
    loads_updated: int = 0
    suppliers_created: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_count": self.row_count,
            "valid_rows": self.valid_rows,
            "errors": [e.__dict__ for e in self.errors],
            "warnings": [w.__dict__ for w in self.warnings],
            "purchase_orders_created": self.purchase_orders_created,
            "purchase_orders_updated": self.purchase_orders_updated,
            "lines_created": self.lines_created,
            "lines_updated": self.lines_updated,
            "containers_created": self.containers_created,
            "loads_created": self.loads_created,
            "loads_updated": self.loads_updated,
            "suppliers_created": self.suppliers_created,
        }


def create_job(t: TenantSession, kind: ImportKind, content: bytes, filename: str | None) -> ImportJob:
    try:
        table = parse_table(content, filename)
    except ImportError_ as e:
        raise Unprocessable(e.message, code=e.code) from e
    signature = header_signature(table.columns)
    saved = t.db.scalar(
        t.q(ImportMapping).where(ImportMapping.kind == kind, ImportMapping.header_signature == signature)
    )
    mapping = dict(saved.mapping) if saved else suggest_mapping(kind, table.columns)
    job = ImportJob(
        kind=kind,
        original_filename=filename,
        sha256=hashlib.sha256(content).hexdigest(),
        content=content,
        encoding=table.encoding,
        delimiter=table.delimiter,
        columns=table.columns,
        mapping=mapping,
        row_count=len(table.rows),
        created_by=t.principal.user_id,
    )
    t.add(job)
    t.db.flush()
    return job


def _check_mapping(kind: ImportKind, mapping: dict[str, str], columns: list[str]) -> None:
    missing = [f for f in REQUIRED[kind] if not mapping.get(f)]
    if missing:
        raise Unprocessable(
            f"Mapping is missing required field(s): {', '.join(missing)}", code="MAPPING_INCOMPLETE"
        )
    unknown = [c for c in mapping.values() if c and c not in columns]
    if unknown:
        raise Unprocessable(
            f"Mapped column(s) not in file: {', '.join(unknown)}", code="MAPPING_UNKNOWN_COLUMN"
        )


def run_job(
    t: TenantSession, job: ImportJob, mapping: dict[str, str], *, dry_run: bool, on_error: str = "skip_rows"
) -> ImportReport:
    """Apply the import inside a SAVEPOINT. Dry run rolls it back; commit keeps it and marks the job DONE."""
    _check_mapping(job.kind, mapping, list(job.columns))
    table = parse_table(bytes(job.content), job.original_filename)
    report = ImportReport(row_count=len(table.rows))

    nested = t.db.begin_nested()
    try:
        if job.kind is ImportKind.PURCHASE_ORDERS:
            _apply_purchase_orders(t, table, mapping, report)
        else:
            _apply_legacy(t, table, mapping, report)
        if report.errors and on_error == "abort":
            raise Unprocessable(
                f"{len(report.errors)} row(s) have errors and on_error=abort", code="IMPORT_ABORTED"
            )
        if report.valid_rows == 0:
            raise Unprocessable("No row could be imported.", code="NO_VALID_ROWS", report=report.to_dict())
        recompute_org(t.db, t.org)
        if dry_run:
            nested.rollback()
        else:
            nested.commit()
    except Exception:
        if nested.is_active:
            nested.rollback()
        raise

    job.mapping = mapping
    job.error_count = len(report.errors)
    job.report = report.to_dict()
    job.status = ImportStatus.DONE if not dry_run else ImportStatus.VALIDATED
    if not dry_run:
        job.committed_at = func.now()
        _remember_mapping(t, job, mapping)
    t.db.flush()
    return report


def _remember_mapping(t: TenantSession, job: ImportJob, mapping: dict[str, str]) -> None:
    signature = header_signature(list(job.columns))
    row = t.db.scalar(
        t.q(ImportMapping).where(ImportMapping.kind == job.kind, ImportMapping.header_signature == signature)
    )
    if row is None:
        t.add(ImportMapping(kind=job.kind, header_signature=signature, mapping=mapping))
    else:
        row.mapping = mapping


# ---------------------------------------------------------------------------- row helpers


class _Row:
    def __init__(self, row_no: int, raw: dict[str, str], mapping: dict[str, str], report: ImportReport):
        self.row_no, self.raw, self.mapping, self.report = row_no, raw, mapping, report
        self.failed = False

    def text(self, field: str) -> str | None:
        col = self.mapping.get(field)
        if not col:
            return None
        v = self.raw.get(col, "").strip()
        return v or None

    def required(self, field: str) -> str | None:
        v = self.text(field)
        if v is None:
            self.error(field, "REQUIRED", f"{field} is empty")
        return v

    def decimal(self, field: str, *, required: bool = False, positive: bool = False) -> Decimal | None:
        raw = self.text(field)
        if raw is None:
            if required:
                self.error(field, "REQUIRED", f"{field} is empty")
            return None
        try:
            v = parse_decimal(raw)
        except ImportError_ as e:
            self.error(field, e.code, e.message)
            return None
        if v is not None and positive and v <= 0:
            self.error(field, "NOT_POSITIVE", f"{field} must be > 0, got {v}")
            return None
        return v

    def date(self, field: str) -> date | None:
        raw = self.text(field)
        if raw is None:
            return None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%Y/%m/%d"):
            try:
                from datetime import datetime

                return datetime.strptime(raw[:10], fmt).date()  # noqa: DTZ007
            except ValueError:
                continue
        self.error(field, "NOT_A_DATE", f"{raw!r} is not a date")
        return None

    def container(self, field: str = "container_number") -> str | None:
        raw = self.text(field)
        if raw is None:
            return None
        v = raw.upper().replace(" ", "")
        if not CONTAINER_NUMBER_RE.match(v):
            self.error(field, "INVALID_CONTAINER_NUMBER", f"{raw!r} is not an ISO 6346 number")
            return None
        return v

    def error(self, field: str, code: str, message: str) -> None:
        self.failed = True
        self.report.errors.append(RowIssue(self.row_no, field, code, message))

    def warn(self, field: str, code: str, message: str) -> None:
        self.report.warnings.append(RowIssue(self.row_no, field, code, message))


def _get_or_create_supplier(t: TenantSession, name: str | None, report: ImportReport) -> Supplier | None:
    if not name:
        return None
    sup = t.db.scalar(t.q(Supplier).where(Supplier.name == name))
    if sup is None:
        sup = t.add(Supplier(name=name))
        t.db.flush()
        report.suppliers_created += 1
    return sup


def _get_or_create_container(t: TenantSession, number: str, report: ImportReport) -> Container:
    c = t.db.scalar(
        t.q(Container).where(Container.container_number == number, Container.archived_at.is_(None))
    )
    if c is None:
        c = t.add(Container(container_number=number))
        t.db.flush()
        report.containers_created += 1
    return c


def _upsert_load(
    t: TenantSession, container: Container, line: PurchaseOrderLine, qty: Decimal, r: _Row
) -> None:
    other_qty = t.db.scalar(
        select(func.coalesce(func.sum(ContainerLoad.quantity), 0)).where(
            ContainerLoad.po_line_id == line.id, ContainerLoad.container_id != container.id
        )
    )
    if Decimal(str(other_qty)) + qty > line.quantity:
        r.error(
            "container_quantity",
            "OVER_ALLOCATED",
            f"{Decimal(str(other_qty)) + qty} loaded exceeds line quantity {line.quantity}",
        )
        return
    load = t.db.scalar(
        select(ContainerLoad).where(
            ContainerLoad.container_id == container.id, ContainerLoad.po_line_id == line.id
        )
    )
    if load is None:
        t.add(ContainerLoad(container_id=container.id, po_line_id=line.id, quantity=qty))
        t.db.flush()
        r.report.loads_created += 1
    elif load.quantity != qty:
        load.quantity = qty
        r.report.loads_updated += 1


def _find_line_without_number(
    t: TenantSession, po: PurchaseOrder | None, sku: str | None, description: str | None
) -> PurchaseOrderLine | None:
    """Rows without line_no identify their line by SKU, else description, else the PO's single line."""
    if po is None:
        return None
    if sku:
        return t.db.scalar(
            select(PurchaseOrderLine).where(PurchaseOrderLine.po_id == po.id, PurchaseOrderLine.sku == sku)
        )
    if description:
        return t.db.scalar(
            select(PurchaseOrderLine).where(
                PurchaseOrderLine.po_id == po.id, PurchaseOrderLine.description == description
            )
        )
    lines = list(t.db.scalars(select(PurchaseOrderLine).where(PurchaseOrderLine.po_id == po.id)))
    return lines[0] if len(lines) == 1 else None


def _apply_purchase_orders(
    t: TenantSession, table: Table, mapping: dict[str, str], report: ImportReport
) -> None:
    seen_lines: set[tuple[str, int]] = set()
    implicit_lines: dict[tuple[str, str], int] = {}  # (po, sku or row marker) -> line_no
    next_line_no: dict[str, int] = {}
    for idx, raw in enumerate(table.rows, start=2):
        r = _Row(idx, raw, mapping, report)
        po_number = r.required("po_number")
        quantity = r.decimal("quantity", required=True, positive=True)
        unit_price = r.decimal("unit_price", required=True)
        if unit_price is not None and unit_price < 0:
            r.error("unit_price", "NEGATIVE", "unit_price must be >= 0")
        currency = (r.text("currency") or t.org.base_currency).upper()
        if len(currency) != 3 or not currency.isalpha():
            r.error("currency", "INVALID_CURRENCY", f"{currency!r} is not a 3-letter ISO code")
        line_no_raw = r.decimal("line_no")
        weight = r.decimal("unit_weight_kg")
        volume = r.decimal("unit_volume_cbm")
        duty = r.decimal("duty_rate")
        if duty is not None and duty > 1:
            duty = duty / 100  # "4,5" or "4,5 %" -> 0.045
        order_date = r.date("order_date")
        container_number = r.container()
        container_qty = r.decimal("container_quantity", positive=True)
        if r.failed or po_number is None or quantity is None or unit_price is None:
            continue

        po = t.db.scalar(t.q(PurchaseOrder).where(PurchaseOrder.po_number == po_number))
        sku = r.text("sku")
        repeated_line = False
        if line_no_raw is not None:
            line_no = int(line_no_raw)
            if (po_number, line_no) in seen_lines:
                r.error("line_no", "DUPLICATE_IN_FILE", f"line {line_no} of {po_number} appears twice")
                continue
            seen_lines.add((po_number, line_no))
        else:
            identity = sku or r.text("description") or ""
            key = (po_number, identity)
            if key in implicit_lines:
                line_no, repeated_line = implicit_lines[key], True
            else:
                existing_line = _find_line_without_number(t, po, sku, r.text("description"))
                if existing_line is not None:
                    line_no = existing_line.line_no
                else:
                    if po_number not in next_line_no:
                        current_max = (
                            t.db.scalar(
                                select(func.coalesce(func.max(PurchaseOrderLine.line_no), 0)).where(
                                    PurchaseOrderLine.po_id == po.id
                                )
                            )
                            if po is not None
                            else 0
                        )
                        next_line_no[po_number] = int(current_max or 0)
                    next_line_no[po_number] += 1
                    line_no = next_line_no[po_number]
                implicit_lines[key] = line_no

        supplier = _get_or_create_supplier(t, r.text("supplier_name"), report)
        if po is None:
            po = t.add(
                PurchaseOrder(
                    po_number=po_number,
                    supplier_id=supplier.id if supplier else None,
                    currency=currency,
                    fx_rate=Decimal("1"),
                    order_date=order_date,
                )
            )
            t.db.flush()
            report.purchase_orders_created += 1
            if currency != t.org.base_currency:
                r.warn(
                    "currency",
                    "FX_RATE_DEFAULTED",
                    f"PO in {currency}: fx_rate set to 1, adjust it on the PO",
                )
        else:
            changed = False
            if supplier and po.supplier_id != supplier.id:
                po.supplier_id, changed = supplier.id, True
            if order_date and po.order_date != order_date:
                po.order_date, changed = order_date, True
            if changed:
                report.purchase_orders_updated += 1

        line = t.db.scalar(
            select(PurchaseOrderLine).where(
                PurchaseOrderLine.po_id == po.id, PurchaseOrderLine.line_no == line_no
            )
        )
        # What the order says, and what someone may have added by hand. The first follows the
        # source; the second is only ever overwritten by a value, never by a blank: an ERP that
        # knows no weights, or a file without the column, must not erase the weights a person
        # typed here so that freight could be split by weight. That erasure would be silent and
        # would repeat at every sync.
        source = {
            "sku": sku,
            "description": r.text("description"),
            "quantity": quantity,
            "unit_price": unit_price,
        }
        enrichment = {
            "hs_code": r.text("hs_code"),
            "unit_weight_kg": weight,
            "unit_volume_cbm": volume,
            "duty_rate": duty,
        }
        if line is None:
            line = t.add(PurchaseOrderLine(po_id=po.id, line_no=line_no, **source, **enrichment))
            t.db.flush()
            report.lines_created += 1
        elif not repeated_line:
            updates = {**source, **{k: v for k, v in enrichment.items() if v is not None}}
            if any(getattr(line, k) != v for k, v in updates.items()):
                for k, v in updates.items():
                    setattr(line, k, v)
                report.lines_updated += 1

        if container_number:
            container = _get_or_create_container(t, container_number, report)
            _upsert_load(t, container, line, container_qty or quantity, r)
            if r.failed:
                continue
        report.valid_rows += 1


def _apply_legacy(t: TenantSession, table: Table, mapping: dict[str, str], report: ImportReport) -> None:
    """Phase 0 format: one row per PO with total_value and an optional container. One line per PO."""
    pct_seen = False
    for idx, raw in enumerate(table.rows, start=2):
        r = _Row(idx, raw, mapping, report)
        po_number = r.required("po_number")
        total = r.decimal("total_value") or Decimal("0")
        container_number = r.container()
        pct = r.decimal("allocation_percentage")
        if pct is not None and not pct_seen:
            pct_seen = True
            r.warn(
                "allocation_percentage",
                "DEPRECATED_COLUMN",
                "allocation_percentage is ignored; costs are allocated by the organization's default method",
            )
        if r.failed or po_number is None:
            continue
        supplier = _get_or_create_supplier(t, r.text("supplier_name"), report)
        po = t.db.scalar(t.q(PurchaseOrder).where(PurchaseOrder.po_number == po_number))
        if po is None:
            po = t.add(
                PurchaseOrder(
                    po_number=po_number,
                    supplier_id=supplier.id if supplier else None,
                    currency=t.org.base_currency,
                )
            )
            t.db.flush()
            report.purchase_orders_created += 1
        line = t.db.scalar(
            select(PurchaseOrderLine).where(PurchaseOrderLine.po_id == po.id, PurchaseOrderLine.line_no == 1)
        )
        if line is None:
            line = t.add(PurchaseOrderLine(po_id=po.id, line_no=1, quantity=Decimal("1"), unit_price=total))
            t.db.flush()
            report.lines_created += 1
        elif line.unit_price != total:
            line.unit_price = total
            report.lines_updated += 1
        if container_number:
            container = _get_or_create_container(t, container_number, report)
            _upsert_load(t, container, line, Decimal("1"), r)
            if r.failed:
                continue
        report.valid_rows += 1


def find_duplicate(t: TenantSession, sha256: str) -> ImportJob | None:
    return t.db.scalar(
        t.q(ImportJob).where(ImportJob.sha256 == sha256, ImportJob.status == ImportStatus.DONE)
    )


def ensure_not_done(job: ImportJob) -> None:
    if job.status is ImportStatus.DONE:
        raise Conflict("This import has already been committed", code="IMPORT_ALREADY_DONE")
