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
PARTIALLY_PUSHED = "partially_pushed"


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
    def pushable(self) -> bool:
        return not self.blockers and bool(self.costs) and self.receipt is not None


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

    existing = _existing_push(db, org, container, by_cost)
    if existing is not None:
        blockers.append(
            Blocker(
                ALREADY_PUSHED,
                f"These costs were already pushed as {existing.odoo_name or existing.odoo_id}.",
                {"existing": existing.odoo_name or str(existing.odoo_id)},
            )
        )
    else:
        overlapping = _overlapping_push(db, org, container, by_cost)
        if overlapping is not None:
            # A landed cost *adds* to the stock valuation. Pushing a set that contains costs an
            # earlier document already carried would charge them to the goods a second time — in
            # someone else's books, where we would not be the ones to notice.
            name = overlapping.odoo_name or str(overlapping.odoo_id)
            shared = len(set(overlapping.cost_ids) & {str(cost_id) for cost_id in by_cost})
            blockers.append(
                Blocker(
                    PARTIALLY_PUSHED,
                    f"{shared} of these costs were already pushed as {name}, and a landed cost adds "
                    "to the stock valuation rather than replacing it, so pushing them again would "
                    "charge the goods twice. Add the new cost by hand in Odoo for now: splitting a "
                    "push into what has already gone and what has not is not decided yet.",
                    {"existing": name, "count": str(shared)},
                )
            )

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
            planned = PlannedCost(
                label=_label(cost),
                cost_ids=[cost_id],
                amount=q2(sum(allocations.values(), Decimal("0.00"))),
            )
            for load_id, amount in allocations.items():
                line = comp.load_rows[load_id].po_line
                move = moves.get(line.sku or "") or moves.get(str(line.id))
                if move is None:
                    blockers.append(
                        Blocker(
                            UNMATCHED_LINE,
                            f"{line.purchase_order.po_number} line {line.line_no} "
                            f"({line.sku or 'no SKU'}) has no matching line on receipt "
                            f"{receipt.name}. Costs are pushed per line, so every line has to match.",
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

    return Plan(
        container_id=container.id,
        container_number=container.container_number,
        receipt=receipt,
        costs=costs,
        blockers=blockers,
        total=q2(sum((cost.amount for cost in costs), Decimal("0.00"))),
        existing_push=existing,
    )


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


def _existing_push(
    db: Session, org: Organization, container: Container, by_cost: dict[UUID, dict[UUID, Decimal]]
) -> ErpPush | None:
    """A push carrying exactly these costs. Anything else is a different push."""
    wanted = {str(cost_id) for cost_id in by_cost}
    if not wanted:
        return None
    for push in db.scalars(
        select(ErpPush)
        .where(ErpPush.org_id == org.id, ErpPush.container_id == container.id)
        .order_by(ErpPush.created_at.desc())
    ):
        if set(push.cost_ids) == wanted:
            return push
    return None


def _overlapping_push(
    db: Session, org: Organization, container: Container, by_cost: dict[UUID, dict[UUID, Decimal]]
) -> ErpPush | None:
    """A push that carried *some* of these costs. Not the same document, and not a safe second one."""
    wanted = {str(cost_id) for cost_id in by_cost}
    if not wanted:
        return None
    for push_row in db.scalars(
        select(ErpPush)
        .where(ErpPush.org_id == org.id, ErpPush.container_id == container.id)
        .order_by(ErpPush.created_at.desc())
    ):
        if set(push_row.cost_ids) & wanted:
            return push_row
    return None


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
    """Write the plan into the ERP as a draft, or return the push that already carried it."""
    prepared = plan(db, org, container, writer, connection)
    if prepared.existing_push is not None:
        return prepared.existing_push, prepared
    if not prepared.pushable:
        from app.core.errors import Unprocessable

        raise Unprocessable(
            "This container cannot be pushed yet: " + "; ".join(b.message for b in prepared.blockers),
            code="ERP_PUSH_BLOCKED",
            blockers=[{"code": b.code, "message": b.message, "params": b.params} for b in prepared.blockers],
        )

    assert prepared.receipt is not None
    cost_ids = sorted(str(cost_id) for cost in prepared.costs for cost_id in cost.cost_ids)
    result = writer.create_landed_cost(
        prepared.receipt.picking_id,
        [
            ErpCostLine(
                label=cost.label,
                amount=f"{cost.amount:.2f}",
                per_move={line.move_id: f"{line.amount:.2f}" for line in cost.lines},
                cost_ids=[str(cost_id) for cost_id in cost.cost_ids],
            )
            for cost in prepared.costs
        ],
        on_date=on_date or datetime.now(UTC).date(),
        reference=f"FreightSight {container.container_number}",
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
