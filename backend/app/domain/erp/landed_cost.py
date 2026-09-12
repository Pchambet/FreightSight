"""Writing our landed cost back into the customer's ERP, under human control.

Two rules, and they are the ones that make a write-back safe to offer at all:

  * **The preview writes nothing.** It builds exactly what would be created and lists what stands in
    the way, so the person clicking sees the object before it exists.
  * **What we create is a draft.** Validating a landed cost posts accounting entries in someone
    else's books; that decision belongs to whoever owns them, in their own screen.

The amounts are ours, per receipt line, because that is the entire point of the integration: Odoo is
told what each line costs rather than asked to guess a split it has no basis for.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Unprocessable
from app.core.money import q2
from app.domain.costing.engine import EXCLUDED_FROM_LANDED
from app.domain.costing.service import Computation, compute
from app.domain.erp.ports import ErpCostLine, ErpReceipt, ErpReceiptLine, ErpWriter
from app.domain.models import (
    Container,
    Cost,
    CostStatus,
    ErpConnection,
    ErpPush,
    Organization,
)

logger = logging.getLogger(__name__)

#: Why a container cannot be pushed. Each one is a sentence a person can act on.
NO_CONNECTION = "no_erp_connection"
NO_COSTS = "no_actual_costs"
NO_RECEIPT = "no_receipt"
MULTIPLE_RECEIPTS = "multiple_receipts"
UNMATCHED_LINE = "unmatched_line"
NOT_VALUED = "not_valued"
ALREADY_PUSHED = "already_pushed"
PUSHED_COST_CHANGED = "pushed_cost_changed"
PUSHED_COST_GONE = "pushed_cost_gone"


def marker_for(cost_ids: Iterable[UUID | str]) -> str:
    """A stable key for *this set of costs*, to recognise our own draft in the ERP.

    Not the container, and not the document's name: the same container is legitimately pushed again
    once another invoice lands, and that second push is a different document. What has to match is
    the set of costs, so the key is their sorted ids, hashed — short enough to sit in a note a human
    might read, and carrying no identifier out of our database into someone else's.
    """
    joined = "|".join(sorted(str(cost_id) for cost_id in cost_ids))
    return hashlib.sha256(joined.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class Blocker:
    """A reason, in English, plus its moving parts on the side.

    `message` is the sentence an API client gets and is not going to change shape. `params` carries
    the same values separately so a screen can build its own sentence in its own language instead of
    showing ours underneath a translated title. Every value is a string, already formatted for
    reading: a list is joined with ", " and a missing SKU is "", so the front decides what "no SKU"
    says rather than parsing our English out of it.
    """

    code: str
    message: str
    params: dict[str, str] = field(default_factory=dict)


@dataclass
class PlannedLine:
    move_id: int
    product_name: str
    sku: str | None
    quantity: str
    amount: Decimal


@dataclass
class PlannedCost:
    label: str
    cost_ids: list[UUID]
    amount: Decimal
    lines: list[PlannedLine] = field(default_factory=list)
    #: Carried through so a second document on the same container gets a reference that tells it
    #: apart from the first. Not in the API response: it is already inside `label`.
    invoice_number: str | None = None
    #: The document that already carries this cost, if one does. Shown so the preview is the whole
    #: picture — what has gone and what has not — rather than only the remainder.
    pushed_as: str | None = None
    #: Its push, so a screen offering "forget this push" has something to name. The document's own
    #: name does not identify it: three drafts on one test instance are called the same thing.
    pushed_push_id: UUID | None = None

    @property
    def pending(self) -> bool:
        return self.pushed_push_id is None


@dataclass
class Plan:
    container_id: UUID
    container_number: str
    receipt: ErpReceipt | None
    costs: list[PlannedCost]
    blockers: list[Blocker]
    total: Decimal
    existing_push: ErpPush | None = None

    @property
    def pending(self) -> list[PlannedCost]:
        """What this push would carry: a landed cost adds to the stock valuation rather than
        replacing it, so a cost a document already holds is never sent a second time."""
        return [cost for cost in self.costs if cost.pending]

    @property
    def pushable(self) -> bool:
        return not self.blockers and bool(self.pending) and self.receipt is not None


def _allocations(comp: Computation, container_id: UUID) -> dict[UUID, dict[UUID, Decimal]]:
    """`cost id -> {load id -> amount}` for the actual costs that reached this container."""
    out: dict[UUID, dict[UUID, Decimal]] = {}
    for allocation in comp.result.allocations:
        load = comp.load_rows.get(allocation.load_id)
        cost = comp.cost_rows.get(allocation.cost_id)
        if load is None or cost is None or load.container_id != container_id:
            continue
        if cost.status is not CostStatus.ACTUAL:
            continue  # an estimate is ours to hold, not theirs to book
        if cost.cost_type.value in EXCLUDED_FROM_LANDED:
            # Recoverable VAT is allocated for the cash view and excluded from the landed cost —
            # the engine's own list, so the two can never drift apart. Pushing it would inflate
            # the customer's stock valuation by a tax they get back.
            continue
        out.setdefault(cost.id, {})[allocation.load_id] = allocation.amount_base
    return out


def plan(
    db: Session,
    org: Organization,
    container: Container,
    writer: ErpWriter | None,
    connection: ErpConnection | None,
) -> Plan:
    """Build what would be written, and everything that stands in the way. Writes nothing."""
    blockers: list[Blocker] = []
    comp = compute(db, org)
    by_cost = _allocations(comp, container.id)

    if connection is None or writer is None:
        blockers.append(
            Blocker(NO_CONNECTION, "This organization has no ERP connection to push anything to.")
        )
    if not by_cost:
        blockers.append(
            Blocker(
                NO_COSTS,
                "No invoiced cost is allocated to this container yet. Estimates are not pushed: "
                "they are ours to hold, not the accounts' to carry.",
            )
        )

    po_numbers = sorted(
        {
            comp.load_rows[load_id].po_line.purchase_order.po_number
            for allocations in by_cost.values()
            for load_id in allocations
        }
    )
    receipts = writer.find_receipts(po_numbers) if writer and po_numbers else []
    receipt = receipts[0] if receipts else None
    if writer and po_numbers and receipt is None:
        blockers.append(
            Blocker(
                NO_RECEIPT,
                f"No done receipt found in the ERP for {', '.join(po_numbers)}. A landed cost "
                "attaches to a receipt, so the goods have to have been received there first.",
                {"po_numbers": ", ".join(po_numbers)},
            )
        )
    if len(receipts) > 1:
        # Several receipts for one container is a real case (a partial delivery), and splitting our
        # costs across them is a decision nobody has made yet. Said out loud rather than guessed.
        blockers.append(
            Blocker(
                MULTIPLE_RECEIPTS,
                f"{len(receipts)} receipts match these orders ("
                + ", ".join(r.name for r in receipts)
                + "). Pushing to one of several receipts is not decided yet; do it by hand for now.",
                {"count": str(len(receipts)), "receipts": ", ".join(r.name for r in receipts)},
            )
        )
        receipt = None

    carried = _carried_costs(db, org, container)
    existing = _latest_live_push(db, org, container)
    blockers.extend(_drift_blockers(live_pushes(db, org, container), comp, by_cost))

    costs: list[PlannedCost] = []
    if receipt is not None:
        moves = _moves_by_sku(receipt)
        unvalued = [line for line in receipt.lines if not line.valued]
        if unvalued:
            names = ", ".join(sorted({line.product_name for line in unvalued}))
            blockers.append(
                Blocker(
                    NOT_VALUED,
                    f"Odoo cannot value a landed cost for {names}: their product category is not in "
                    "automated valuation with a real cost method (FIFO or average). Odoo refuses "
                    "this at validation, so it is refused here instead.",
                    {"products": names},
                )
            )
        for cost_id, allocations in sorted(by_cost.items(), key=lambda item: str(item[0])):
            cost = comp.cost_rows[cost_id]
            already = carried.get(str(cost_id))
            planned = PlannedCost(
                label=_label(cost),
                cost_ids=[cost_id],
                amount=q2(sum(allocations.values(), Decimal("0.00"))),
                invoice_number=cost.invoice_number,
                pushed_as=(already.odoo_name or str(already.odoo_id)) if already else None,
                pushed_push_id=already.id if already else None,
            )
            for load_id, amount in allocations.items():
                line = comp.load_rows[load_id].po_line
                move = moves.get(line.sku or "") or moves.get(str(line.id))
                if move is None:
                    if planned.pending:
                        # Only what this push would carry can block it. A cost that already went
                        # is history; whether its line still matches today changes nothing.
                        blockers.append(
                            Blocker(
                                UNMATCHED_LINE,
                                f"{line.purchase_order.po_number} line {line.line_no} "
                                f"({line.sku or 'no SKU'}) has no matching line on receipt "
                                f"{receipt.name}. Costs are pushed per line, so every line has "
                                "to match.",
                                {
                                    "po_number": line.purchase_order.po_number,
                                    "line_no": str(line.line_no),
                                    "sku": line.sku or "",
                                    "receipt": receipt.name,
                                },
                            )
                        )
                    continue
                planned.lines.append(
                    PlannedLine(
                        move_id=move.move_id,
                        product_name=move.product_name,
                        sku=move.sku,
                        quantity=move.quantity,
                        amount=q2(amount),
                    )
                )
            costs.append(planned)

    prepared = Plan(
        container_id=container.id,
        container_number=container.container_number,
        receipt=receipt,
        costs=costs,
        blockers=blockers,
        # Only what would go: a total counting what has already been written would be the amount of
        # a document nobody is about to create.
        total=q2(sum((cost.amount for cost in costs if cost.pending), Decimal("0.00"))),
        existing_push=existing,
    )
    if costs and not prepared.pending:
        joined = ", ".join(sorted({cost.pushed_as for cost in costs if cost.pushed_as}))
        blockers.append(
            Blocker(
                ALREADY_PUSHED,
                f"Every invoiced cost on this container has already been pushed, as {joined}. "
                "There is nothing left to write; a new invoice on this container becomes a new "
                "document of its own.",
                {"existing": joined},
            )
        )
    return prepared


def _reference(container: Container, costs: list[PlannedCost]) -> str:
    """The document's name in the ERP.

    The container alone is no longer enough now that one container legitimately has several
    documents — a later invoice is a document of its own — and three drafts called the same thing
    tell an accountant nothing and make our own "already pushed as …" ambiguous. The invoices this
    one carries are what distinguish it.
    """
    base = f"FreightSight {container.container_number}"
    invoices = sorted({cost.invoice_number for cost in costs if cost.invoice_number})
    if not invoices:
        return base
    return f"{base} — {', '.join(invoices)}"[:120]


def forget(
    db: Session,
    org: Organization,
    push_row: ErpPush,
    writer: ErpWriter | None,
    *,
    actor_user_id: UUID | None = None,
    reason: str | None = None,
) -> ErpPush:
    """Stop a push from holding its costs, so they can be pushed again. Never deletes the row.

    Only once the document it made is really gone from the ERP: forgetting a push whose draft is
    still there would let the same charge be written into the customer's books a second time, which
    is the exact accident this whole mechanism exists to prevent.
    """
    if push_row.forgotten_at is not None:
        raise Conflict("This push has already been forgotten.", code="ERP_PUSH_ALREADY_FORGOTTEN")
    if writer is None:
        raise Unprocessable(
            "The ERP connection is gone, so we cannot check whether the document is still there. "
            "Reconnect the ERP and try again: forgetting a push whose document still exists would "
            "let the same costs be charged to the goods twice.",
            code="ERP_NO_CONNECTION",
        )
    document = writer.read_landed_cost(push_row.odoo_id)
    if document is not None:
        raise Conflict(
            f"{document.name or document.record_id} is still in the ERP, in {document.state}. "
            "Delete it there first: while it exists it carries these costs, and forgetting the "
            "push would let them be written a second time.",
            code="ERP_DOCUMENT_STILL_THERE",
            document={"id": document.record_id, "name": document.name, "state": document.state},
        )
    push_row.forgotten_at = datetime.now(UTC)
    push_row.forgotten_reason = reason
    push_row.forgotten_by = actor_user_id
    db.flush()
    logger.info(
        "forgot an erp push",
        extra={"push_id": str(push_row.id), "odoo_id": push_row.odoo_id, "org_id": str(org.id)},
    )
    return push_row


def _drift_blockers(
    pushes: list[ErpPush], comp: Computation, by_cost: dict[UUID, dict[UUID, Decimal]]
) -> list[Blocker]:
    """What has changed on our side since a document was written, and now differs from it.

    A draft in the ERP is a copy of a moment. A cost edited afterwards (amount, rate, method, the
    loads it spreads over) or deleted leaves that copy carrying a figure nobody can see from here,
    and the next push would add to it rather than fix it. So it blocks, and says what to do: delete
    the draft over there, forget the push here, push again — three steps a person can check.
    """
    out: list[Blocker] = []
    for push_row in pushes:
        name = push_row.odoo_name or str(push_row.odoo_id)
        gone: list[str] = []
        changed: list[str] = []
        for cost_id in push_row.cost_ids:
            try:
                key = UUID(cost_id)
            except ValueError:  # pragma: no cover - our own rows
                continue
            snapshot = (push_row.carried or {}).get(cost_id) or {}
            allocations = by_cost.get(key)
            if allocations is None:
                cost = comp.cost_rows.get(key)
                gone.append(_label(cost) if cost is not None else snapshot.get("label") or cost_id[:8])
                continue
            recorded = snapshot.get("amount")
            if recorded is None:
                continue  # written before amounts were kept: nothing to compare against
            current = q2(sum(allocations.values(), Decimal("0.00")))
            if current != Decimal(recorded):
                changed.append(f"{_label(comp.cost_rows[key])}: {Decimal(recorded):.2f} → {current:.2f}")
        if gone:
            out.append(
                Blocker(
                    PUSHED_COST_GONE,
                    f"{name} carries {', '.join(gone)}, which no longer counts on this container "
                    "(deleted, closed or moved). The draft still holds it. Delete the draft in the "
                    "ERP, forget the push here, then push again.",
                    {"existing": name, "costs": ", ".join(gone), "count": str(len(gone))},
                )
            )
        if changed:
            out.append(
                Blocker(
                    PUSHED_COST_CHANGED,
                    f"{name} was written with amounts that have changed since ({'; '.join(changed)}). "
                    "The draft still carries the old figures. Delete the draft in the ERP, forget the "
                    "push here, then push again.",
                    {"existing": name, "changes": "; ".join(changed), "count": str(len(changed))},
                )
            )
    return out


def _label(cost: Cost) -> str:
    parts = [cost.cost_type.value.replace("_", " ").title()]
    if cost.invoice_number:
        parts.append(f"invoice {cost.invoice_number}")
    if cost.vendor:
        parts.append(cost.vendor)
    return " — ".join(parts)


def _moves_by_sku(receipt: ErpReceipt) -> dict[str, ErpReceiptLine]:
    """Receipt lines by SKU. The SKU is the only identifier both systems agree on."""
    out: dict[str, ErpReceiptLine] = {}
    for line in receipt.lines:
        if line.sku:
            out.setdefault(line.sku, line)
    return out


def live_pushes(db: Session, org: Organization, container: Container) -> list[ErpPush]:
    """The pushes on this container that still hold their costs, newest first."""
    return list(
        db.scalars(
            select(ErpPush)
            .where(
                ErpPush.org_id == org.id,
                ErpPush.container_id == container.id,
                ErpPush.forgotten_at.is_(None),
            )
            .order_by(ErpPush.created_at.desc())
        )
    )


def _carried_costs(db: Session, org: Organization, container: Container) -> dict[str, ErpPush]:
    """`cost id -> the document that already carries it`, oldest push winning a tie."""
    out: dict[str, ErpPush] = {}
    for push_row in reversed(live_pushes(db, org, container)):
        for cost_id in push_row.cost_ids:
            out[cost_id] = push_row
    return out


def _latest_live_push(db: Session, org: Organization, container: Container) -> ErpPush | None:
    """What a push with nothing new to say returns, so a double click is not an error."""
    pushes = live_pushes(db, org, container)
    return pushes[0] if pushes else None


def push(
    db: Session,
    org: Organization,
    container: Container,
    writer: ErpWriter,
    connection: ErpConnection,
    *,
    created_by: UUID | None = None,
    on_date: date | None = None,
) -> tuple[ErpPush, Plan]:
    """Write what no document carries yet into the ERP, as a draft.

    Only the costs that are still pending: a landed cost adds to the stock valuation rather than
    replacing it, so re-sending a cost an earlier document already holds charges the goods twice —
    in someone else's books, where we would not be the ones to notice. When nothing is pending the
    most recent push comes back instead of an error, so clicking twice is not a mistake.
    """
    prepared = plan(db, org, container, writer, connection)
    if not prepared.pending and prepared.existing_push is not None:
        return prepared.existing_push, prepared
    if not prepared.pushable:
        raise Unprocessable(
            "This container cannot be pushed yet: " + "; ".join(b.message for b in prepared.blockers),
            code="ERP_PUSH_BLOCKED",
            blockers=[{"code": b.code, "message": b.message, "params": b.params} for b in prepared.blockers],
        )

    assert prepared.receipt is not None
    pending = prepared.pending
    cost_ids = sorted(str(cost_id) for cost in pending for cost_id in cost.cost_ids)
    result = writer.create_landed_cost(
        prepared.receipt.picking_id,
        [
            ErpCostLine(
                label=cost.label,
                amount=f"{cost.amount:.2f}",
                per_move={line.move_id: f"{line.amount:.2f}" for line in cost.lines},
                cost_ids=[str(cost_id) for cost_id in cost.cost_ids],
            )
            for cost in pending
        ],
        on_date=on_date or datetime.now(UTC).date(),
        reference=_reference(container, pending),
        marker=marker_for(cost_ids),
    )
    if result.adopted:
        # The ERP write of an earlier attempt survived; ours did not. Worth a line: it is the only
        # trace that anything went wrong, and the customer's books are unharmed either way.
        logger.info(
            "adopted an existing landed cost draft",
            extra={"odoo_id": result.record_id, "container_id": str(container.id)},
        )
    record = ErpPush(
        org_id=org.id,
        connection_id=connection.id,
        container_id=container.id,
        cost_ids=cost_ids,
        carried={
            str(cost_id): {"amount": f"{cost.amount:.2f}", "label": cost.label}
            for cost in pending
            for cost_id in cost.cost_ids
        },
        odoo_model=result.model,
        odoo_id=result.record_id,
        odoo_name=result.name,
        status=result.state,
        # Prefixed, so it cannot be mistaken for a field Odoo sent us.
        response={**result.raw, "freightsight_adopted": result.adopted},
        created_by=created_by,
    )
    db.add(record)
    db.flush()
    return record, prepared
