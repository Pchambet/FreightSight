"""What we verify ourselves, whatever read the invoice.

An extractor — regex or model — is a witness, not an authority. These checks are the arithmetic and
the tenancy facts that no witness gets to overrule:

  * the lines plus VAT have to add up to the stated total, to the cent (0.02 of slack for the
    supplier's own rounding). They usually do not, because a charge was missed — so the confidence
    is capped and a person is told which way it is out;
  * a container reference only survives if it is a container this organization actually has. A model
    handed a list can still return something that is not on it;
  * a currency with no ECB rate for the invoice date cannot become a cost silently.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.fx.service import FxService
from app.domain.invoices.ports import ExtractionContext, FreightInvoice
from app.domain.models import CostScope, CostType

#: How far the sum of the lines may be from the stated total before we stop believing the reading.
TOLERANCE = Decimal("0.02")
#: The ceiling applied to a reading whose arithmetic does not hold.
CAPPED_CONFIDENCE = 0.5


@dataclass
class CheckedLine:
    description: str
    amount: Decimal
    currency: str
    cost_type: CostType | None
    scope: CostScope | None
    target_id: UUID | None
    confidence: float
    notes: list[str]


@dataclass
class CheckedInvoice:
    invoice: FreightInvoice
    lines: list[CheckedLine]
    confidence: float
    notes: list[str]


def arithmetic_holds(invoice: FreightInvoice) -> tuple[bool, Decimal | None]:
    """Whether Σ lines + VAT equals the stated total. Returns the difference when it does not."""
    if invoice.total is None:
        return True, None
    try:
        total = Decimal(invoice.total)
    except ArithmeticError:  # pragma: no cover - the model validated it
        return False, None
    line_sum = sum((ln.decimal() or Decimal(0) for ln in invoice.lines), Decimal(0))
    vat = Decimal(invoice.vat) if invoice.vat else Decimal(0)
    difference = (line_sum + vat - total).quantize(Decimal("0.01"))
    return abs(difference) <= TOLERANCE, difference


def check(
    db: Session,
    fx: FxService,
    invoice: FreightInvoice,
    context: ExtractionContext,
    *,
    base_currency: str,
    invoice_date: date | None,
) -> CheckedInvoice:
    """Turn a reading into reviewable lines, saying on each one what a person should look at."""
    holds, difference = arithmetic_holds(invoice)
    confidence = invoice.confidence if holds else min(invoice.confidence, CAPPED_CONFIDENCE)
    notes: list[str] = list(invoice.notes)
    if not holds and difference is not None:
        direction = "more than" if difference > 0 else "less than"
        notes.append(
            f"The charges read add up to {abs(difference)} {direction} the invoice total: "
            "a line is probably missing or misread."
        )

    # When the invoice names exactly one container we know, every charge on it is about that box.
    # This is the ordinary case — a forwarder invoices per container — and it is deterministic, so
    # it is decided here rather than left to whatever read the document.
    known = [n for n in {c.upper() for c in invoice.container_numbers} if n in context.containers]
    single_container = known[0] if len(known) == 1 else None

    checked: list[CheckedLine] = []
    for line in invoice.lines:
        amount = line.decimal()
        if amount is None or amount <= 0:
            continue
        currency = (line.currency or invoice.currency or base_currency).upper()
        line_notes: list[str] = []
        line_confidence = min(line.confidence, confidence)

        scope: CostScope | None = None
        target_id = None
        if line.container_number:
            container_id = context.containers.get(line.container_number.upper())
            if container_id is not None:
                scope, target_id = CostScope.CONTAINER, container_id
            else:
                # The model was given the list of this organization's containers and answered with
                # something else. It is dropped, and said out loud rather than silently.
                line_notes.append(
                    f"{line.container_number} is not one of this organization's containers; "
                    "the target needs choosing by hand."
                )
                line_confidence = min(line_confidence, CAPPED_CONFIDENCE)
        elif line.po_number:
            po_id = context.purchase_orders.get(line.po_number.upper())
            if po_id is not None:
                scope, target_id = CostScope.PO, po_id
        elif single_container is not None:
            scope, target_id = CostScope.CONTAINER, context.containers[single_container]
            line_notes.append(f"Charged to {single_container}, the only container named on the invoice.")

        if not _rate_available(db, fx, base_currency, currency, invoice_date):
            line_notes.append(
                f"No {currency} reference rate for {invoice_date or 'this date'}: "
                "the rate has to be entered by hand before this line can be confirmed."
            )
            line_confidence = min(line_confidence, CAPPED_CONFIDENCE)

        checked.append(
            CheckedLine(
                description=line.description[:500],
                amount=amount,
                currency=currency,
                cost_type=line.cost_type,
                scope=scope,
                target_id=target_id,
                confidence=round(line_confidence, 2),
                notes=line_notes,
            )
        )

    if len(invoice.container_numbers) > 1:
        notes.append("This invoice mentions several containers; check that each charge is on the right one.")
    return CheckedInvoice(invoice=invoice, lines=checked, confidence=round(confidence, 2), notes=notes)


def _rate_available(db: Session, fx: FxService, base: str, quote: str, on_date: date | None) -> bool:
    if quote == base or on_date is None:
        return True
    try:
        fx.resolve(db, base, quote, on_date)
    except Exception:
        return False
    return True
