"""Taking a file back.

A file is dropped to be read; the wrong export, a month too many, a column mapped the wrong way
round, and what it wrote is wrong. Taking the file back deletes exactly what it created — a cost
names the import it came from, and the job keeps the other rows it created (`ImportJob.created`) —
and nothing else: a row that was there before, and that the file only changed, keeps what it now
says. A file that was never imported wrote nothing, and is simply discarded.

The line is drawn where the confirmation of an invoice draws it: once a cost has gone into the
customer's own books, through an ERP document, or into a closed month, deleting it here would leave
their valuation or their close carrying a figure nothing on our side remembers. Those are refused, by
name, and corrected the way a posted document is — with another one.

And nothing is pulled from under what stands on it. A later copy of the same ledger that recognised
some of these lines, the costs a later file put on these containers, the orders a tracking sheet
loaded into them, the same orders said again by a later file (`ImportJob.matched`): the later file
is taken back first, by name — and rows an ERP sync now keeps in step are no longer this file's to
take. What a person did by hand on these rows — a cost typed in or confirmed from an invoice, an
order loaded in a container — is named too, and is theirs to remove; a line a person added to an
order of the file is not the file's, and keeps its order.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, String, any_, delete, literal, or_, select
from sqlalchemy.dialects.postgresql import ARRAY, array
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.core.errors import Conflict, Unprocessable
from app.core.tenancy import TenantSession
from app.domain.costing.service import recompute_org
from app.domain.imports.containers import UNKNOWN_CONTAINER
from app.domain.invoices.checks import note_field
from app.domain.invoices.service import _live_pushes_carrying
from app.domain.models import (
    Alert,
    Container,
    ContainerLoad,
    Cost,
    CostAllocation,
    ErpSyncRun,
    ImportJob,
    ImportKind,
    ImportStatus,
    InvoiceLine,
    Product,
    PurchaseOrder,
    PurchaseOrderLine,
    Shipment,
    Supplier,
)
from app.domain.periods.service import frozen_periods

#: How many containers, orders or invoices a refusal names before it only counts them.
NAMED = 5


def _among(column: Any, ids: Collection[UUID]) -> ColumnElement[bool]:
    """`column` is one of `ids`, bound as one array: a file's rows are counted in tens of thousands,
    and a statement holds no more than 65 535 parameters."""
    return column == any_(literal(list(ids), ARRAY(PG_UUID(as_uuid=True))))  # type: ignore[no-any-return]


def _lists_any(listed: Any, ids: Collection[UUID]) -> ColumnElement[bool]:
    """A job's list of rows (`created` or `matched`, one table of it) names one of `ids`."""
    return listed.has_any(literal([str(i) for i in ids], ARRAY(String)))  # type: ignore[no-any-return]


def synced_jobs(t: TenantSession, ids: Collection[UUID]) -> set[UUID]:
    """The jobs among `ids` an ERP sync drove. An ERP sync writes a file too; the sync run that drove
    the job is the record of it, so nothing has to be stored on the job. A large sync is several
    files: the run links the first, and lists every one in its detail."""
    if not ids:
        return set()
    listed = ErpSyncRun.detail["import_job_ids"]
    runs = t.db.execute(
        select(ErpSyncRun.import_job_id, listed)
        .where(ErpSyncRun.org_id == t.org_id)
        .where(or_(ErpSyncRun.import_job_id.in_(list(ids)), listed.has_any(array([str(i) for i in ids]))))
    ).all()
    named: set[str] = set()
    for first, every in runs:
        named.update([str(first)] if first is not None else [], every or [])
    return {i for i in ids if str(i) in named}


@dataclass
class TakenBack:
    """What taking a file back removed."""

    #: The file had never been imported: nothing was written, the draft is gone.
    discarded: bool = False
    cost_ids: list[UUID] = field(default_factory=list)
    #: Estimates the deleted costs had replaced, standing again.
    estimates_reopened: int = 0
    #: The other rows deleted, by table. A container is archived, as when deleted by hand.
    rows: dict[str, int] = field(default_factory=dict)


def undoable(job: ImportJob, *, synced: bool) -> bool:
    """Dropped by a person and not taken back yet: a file never imported (nothing to delete, it is
    discarded), a costs file, or a file whose rows are on record. What happened to its rows since is
    for `undo` to refuse, by name."""
    if synced or job.undone_at is not None:
        return False
    if job.status is not ImportStatus.DONE:
        return True
    return job.kind is ImportKind.COSTS or job.created is not None


def undo(t: TenantSession, job: ImportJob, *, synced: bool) -> TakenBack:
    """Delete what the file created, in the caller's transaction."""
    if job.undone_at is not None:
        raise Conflict(
            "This import was already taken back",
            code="IMPORT_ALREADY_UNDONE",
            undone_at=job.undone_at.isoformat(),
        )
    if not undoable(job, synced=synced):
        raise Unprocessable(
            "Only a file a person dropped, whose rows are on record, can be taken back",
            code="IMPORT_NOT_UNDOABLE",
            kind=job.kind.value,
            status=job.status.value,
        )
    if job.status is not ImportStatus.DONE:
        t.db.delete(job)
        t.db.flush()
        return TakenBack(discarded=True)
    taken = _take_back_costs(t, job) if job.kind is ImportKind.COSTS else _take_back_rows(t, job)
    job.undone_at = datetime.now(UTC)
    t.db.flush()
    recompute_org(t.db, t.org)
    return taken


def _take_back_costs(t: TenantSession, job: ImportJob) -> TakenBack:
    costs = list(t.db.scalars(t.q(Cost).where(Cost.import_job_id == job.id)))
    mine = {str(cost.id) for cost in costs}
    relying = [
        (later_id, name)
        for later_id, name, matched in t.db.execute(
            select(ImportJob.id, ImportJob.original_filename, ImportJob.matched_cost_ids)
            .where(
                ImportJob.org_id == t.org_id,
                ImportJob.id != job.id,
                ImportJob.kind == ImportKind.COSTS,
                ImportJob.status == ImportStatus.DONE,
                ImportJob.undone_at.is_(None),
            )
            .order_by(ImportJob.committed_at)
        )
        if mine & set(matched or [])
    ]
    if relying:
        raise Unprocessable(
            "A later costs file recognised some of these lines and left them to this one; take it back first",
            code="IMPORT_RELIED_ON",
            import_ids=[str(later_id) for later_id, _ in relying],
            files=[name or "" for _, name in relying],
        )
    credited = [credit for cost in costs for credit in cost.credits]
    if credited:
        # Deleting the cost would take its refunds with it, out of the history and off the credit note
        # that took them: they are taken back first, as for a cost deleted by hand.
        raise Unprocessable(
            "A credit has reduced some of these costs; take the credits back first",
            code="COST_HAS_CREDITS",
            params={"credit_number": credited[0].credit_number or "", "count": str(len(credited))},
        )
    pushed = _live_pushes_carrying(t.db, t.org, costs)
    if pushed:
        raise Unprocessable(
            "Some of these costs are in the ERP; correct them there with an adjustment document, or "
            "forget the push first",
            code="COSTS_PUSHED_TO_ERP",
            errors=[
                {
                    "field": "erp",
                    "code": "COSTS_PUSHED_TO_ERP",
                    "message": (
                        f"@pushed_cost|{note_field(push.odoo_name or str(push.odoo_id))}|{push.status}"
                    ),
                }
                for push in pushed
            ],
        )
    ids = [cost.id for cost in costs]
    boxes = {cost.container_id for cost in costs if cost.container_id is not None}
    if ids:
        boxes |= set(
            t.db.scalars(
                select(ContainerLoad.container_id)
                .join(CostAllocation, CostAllocation.container_load_id == ContainerLoad.id)
                .where(CostAllocation.cost_id.in_(ids))
            )
        )
    _refuse_closed_months(t, boxes)
    reopened = sum(1 for cost in costs if cost.supersedes_cost_id is not None)
    for cost in costs:
        t.db.delete(cost)
    return TakenBack(cost_ids=ids, estimates_reopened=reopened)


def _refuse_closed_months(t: TenantSession, boxes: set[UUID]) -> None:
    frozen = frozen_periods(t.db, t.org_id)
    months = sorted({frozen[box] for box in boxes if box in frozen})
    if months:
        raise Unprocessable(
            "Some of these rows are in a closed month; reopen it first",
            code="IMPORT_PERIOD_CLOSED",
            months=months,
        )


def _release_invoice_lines(t: TenantSession, gone: set[UUID], boxes: dict[UUID, str]) -> None:
    """A line of an invoice that pointed at a row now gone points at nothing again — whatever the
    invoice's state: one being reviewed is confirmed next, one rejected can be reopened as it stands,
    and either would put its cost on a container that is no longer there. A box is named on the line
    as the reading names one nobody knows, so the next tracking sheet finds the line."""
    for line in t.db.scalars(t.q(InvoiceLine).where(_among(InvoiceLine.target_id, gone))):
        number = boxes.get(line.target_id) if line.target_id is not None else None
        line.scope, line.target_id = None, None
        if number is not None:
            notes = [note.strip() for note in (line.notes or "").split(";") if note.strip()]
            kept = [note for note in notes if not note.startswith("@single_container|")]
            line.notes = "; ".join([*kept, f"{UNKNOWN_CONTAINER}{number}"])


def _on_record(job: ImportJob, model: type) -> list[UUID]:
    return [UUID(i) for i in (job.created or {}).get(model.__tablename__, [])]  # type: ignore[attr-defined]


def _take_back_rows(t: TenantSession, job: ImportJob) -> TakenBack:
    """A price list, an orders file or a tracking sheet: the rows it created go, in the order their
    foreign keys allow, once nothing stands on them. They are locked first: a load written on one of
    them at the same moment is then either seen, and holds the file, or refused."""
    db = t.db

    def mine(model: type) -> Any:
        return t.q(model).where(_among(model.id, _on_record(job, model))).with_for_update()  # type: ignore[attr-defined]

    loads = list(db.scalars(mine(ContainerLoad)))
    boxes = list(db.scalars(mine(Container).where(Container.archived_at.is_(None))))
    lines = list(db.scalars(mine(PurchaseOrderLine)))
    created_orders = list(db.scalars(mine(PurchaseOrder)))
    shipments = list(db.scalars(mine(Shipment)))
    products = list(db.scalars(mine(Product)))
    load_ids, box_ids, line_ids = ({row.id for row in rows} for rows in (loads, boxes, lines))
    shipment_ids = {shipment.id for shipment in shipments}
    # An order of the file that now holds a line the file did not create — added by hand, by a later
    # file, by the ERP — stays, with that line: only what the file created is the file's to delete.
    kept_orders = set(
        db.scalars(
            select(PurchaseOrderLine.po_id).where(
                _among(PurchaseOrderLine.po_id, [order.id for order in created_orders]),
                ~_among(PurchaseOrderLine.id, line_ids),
            )
        )
    )
    orders = [order for order in created_orders if order.id not in kept_orders]
    order_ids = {order.id for order in orders}

    # What stands on these rows and is not this file's: a load, on a line or in a box that goes…
    standing = list(
        db.scalars(
            t.q(ContainerLoad).where(
                or_(_among(ContainerLoad.po_line_id, line_ids), _among(ContainerLoad.container_id, box_ids)),
                ~_among(ContainerLoad.id, load_ids),
            )
        )
    )
    # …and a cost whose spread would move: on a box whose loads change, on the bill such a box
    # travels on, on a line whose loads change or on its order. Found by what the cost is on, not by
    # what it is spread over: a cost that could not be spread yet would move all the same.
    touched = box_ids | {load.container_id for load in loads}
    moved_lines = line_ids | {load.po_line_id for load in loads}
    on_bills = select(Container.shipment_id).where(_among(Container.id, touched))
    bills = shipment_ids | {bill for bill in db.scalars(on_bills) if bill is not None}
    moved_orders = order_ids | set(
        db.scalars(select(PurchaseOrderLine.po_id).where(_among(PurchaseOrderLine.id, moved_lines)))
    )
    costs = list(
        db.scalars(
            t.q(Cost).where(
                or_(
                    _among(Cost.container_id, touched),
                    _among(Cost.shipment_id, bills),
                    _among(Cost.po_id, moved_orders),
                    _among(Cost.po_line_id, moved_lines),
                )
            )
        )
    )

    # Another file is taken back first, by name: the costs file that put costs here, the file that
    # loaded these orders or these boxes, and any file that found these rows already there and spoke
    # about them — the same orders said again, a price list repriced, a box dated by the tracking.
    going = {
        Product: {product.id for product in products},
        PurchaseOrder: order_ids,
        PurchaseOrderLine: line_ids,
        Container: box_ids,
        ContainerLoad: load_ids,
    }
    held = [_lists_any(ImportJob.matched[model.__tablename__], ids) for model, ids in going.items() if ids]
    if standing:
        held.append(
            _lists_any(ImportJob.created[ContainerLoad.__tablename__], {load.id for load in standing})
        )
    cost_jobs = {cost.import_job_id for cost in costs if cost.import_job_id is not None}
    if cost_jobs:
        held.append(ImportJob.id.in_(cost_jobs))
    relying = (
        db.execute(
            select(ImportJob.id, ImportJob.original_filename)
            .where(
                ImportJob.org_id == t.org_id,
                ImportJob.id != job.id,
                ImportJob.status == ImportStatus.DONE,
                ImportJob.undone_at.is_(None),
                or_(*held),
            )
            .order_by(ImportJob.committed_at.desc(), ImportJob.created_at.desc())
        ).all()
        if held
        else []
    )
    if synced_jobs(t, [later_id for later_id, _ in relying]):
        # An ERP sync cannot be taken back, and will say these rows again: they are the ERP's now.
        raise Unprocessable(
            "An ERP sync now keeps rows of this file in step; correct them in the ERP",
            code="IMPORT_HELD_BY_ERP_SYNC",
        )
    if relying:
        raise Unprocessable(
            "A later file stands on rows of this one; take it back first",
            code="IMPORT_RELIED_ON",
            import_ids=[str(later_id) for later_id, _ in relying],
            files=[name or "" for _, name in relying],
        )
    numbers: dict[UUID, str] = {
        box_id: number
        for box_id, number in db.execute(
            select(Container.id, Container.container_number).where(
                Container.org_id == t.org_id,
                _among(Container.id, touched | {load.container_id for load in standing}),
            )
        )
    }
    if standing:
        # Loaded by hand, or by a file that can no longer say so.
        named = sorted({numbers[load.container_id] for load in standing})
        raise Unprocessable(
            "Orders were loaded in containers outside this file; unload them first",
            code="IMPORT_ROWS_LOADED",
            count=len(named),
            containers=named[:NAMED],
        )
    if costs:
        # Typed in, estimated, or confirmed from an invoice: a person's, and theirs to remove.
        named = sorted({numbers[cost.container_id] for cost in costs if cost.container_id in numbers})
        invoices = sorted({cost.invoice_number for cost in costs if cost.invoice_number})
        raise Unprocessable(
            "Costs stand on rows of this file; delete them first",
            code="IMPORT_ROWS_CARRY_COSTS",
            count=len(costs),
            containers=named[:NAMED],
            invoices=invoices[:NAMED],
        )
    _refuse_closed_months(t, touched)

    for load in loads:
        db.delete(load)
    db.flush()
    now = datetime.now(UTC)
    for box in boxes:
        # As when a container is deleted by hand: archived, so that what was said about it stays
        # readable. The bell's alerts about it go with it.
        box.archived_at = now
        if box.shipment_id in shipment_ids:
            box.shipment_id = None
    if boxes:
        db.execute(delete(Alert).where(Alert.org_id == t.org_id, _among(Alert.container_id, box_ids)))
    db.flush()
    # A bill of lading goes with the boxes the file put on it, unless another box travels on it.
    kept_bills = set(
        db.scalars(select(Container.shipment_id).where(_among(Container.shipment_id, shipment_ids)))
    )
    gone_shipments = [shipment for shipment in shipments if shipment.id not in kept_bills]
    for shipment in gone_shipments:
        db.delete(shipment)
    _release_invoice_lines(
        t,
        box_ids | {shipment.id for shipment in gone_shipments} | order_ids | line_ids,
        {box.id: box.container_number for box in boxes},
    )
    for line in lines:
        if line.po_id not in order_ids:
            db.delete(line)
    for order in orders:
        db.delete(order)  # with its lines, all of them the file's
    for product in products:
        # Order lines keep what they copied: deleting an entry moves no landed cost.
        db.delete(product)
    db.flush()
    # A supplier the file introduced goes once no order names it.
    still_named = set(db.scalars(t.q(PurchaseOrder).with_only_columns(PurchaseOrder.supplier_id)))
    suppliers = [
        supplier
        for supplier in db.scalars(t.q(Supplier).where(_among(Supplier.id, _on_record(job, Supplier))))
        if supplier.id not in still_named
    ]
    for supplier in suppliers:
        db.delete(supplier)
    counts = {
        Product: len(products),
        Supplier: len(suppliers),
        PurchaseOrder: len(orders),
        PurchaseOrderLine: len(lines),
        Container: len(boxes),
        Shipment: len(gone_shipments),
        ContainerLoad: len(loads),
    }
    return TakenBack(rows={model.__tablename__: n for model, n in counts.items() if n})
