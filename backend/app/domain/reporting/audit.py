"""The audit of a closed period: what the goods really cost, and what is worth a claim.

This is the document the paid offer is made of — "your last quarter, audited" — and the quarterly
report a CFO puts in front of the owner. One rule governs it: **a finding is never an accusation and
never a promised saving.** Every line is a measured fact, with the objects behind it and the rule
that produced it; the total is called "amounts to check", not "savings". Each finding carries,
separately, how much money it is about (`amount`) and how sure the rule is (`confidence`): a duplicate
invoice line, an invoice above the quote it replaced, an estimate nobody invoiced are facts; a charge
that is merely far above the median of its route is a question, and says so.

Everything here comes from one computation of the engine (`Computation`), the same the screens use,
and the figures of the sections it shares with other reports are those reports' figures for the same
dates — tested against them.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from statistics import median
from typing import Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.money import q2, q4
from app.domain.costing.engine import EXCLUDED_FROM_LANDED
from app.domain.costing.service import Computation
from app.domain.models import Container, Cost, CostStatus, Invoice, InvoiceStatus, Organization
from app.domain.reporting.service import Bucket, _route, arrival_date, dnd_report, landed_cost_report
from app.domain.reporting.skus import SkuSummary, sku_report

ZERO = Decimal("0.00")
Confidence = Literal["sure", "to_check"]

#: A charge of the same type, on the same container, from another invoice, this close in amount is
#: the same charge billed twice — and not "two handlings": those come on one invoice as one line.
DUPLICATE_TOLERANCE = Decimal("0.02")
#: An invoice is "above its quote" from five per cent and fifty euros: below that it is a bunker
#: surcharge or a rounding, and a claim for it would cost more than it brings.
ABOVE_QUOTE_MIN_SHARE = Decimal("0.05")
ABOVE_QUOTE_MIN_AMOUNT = Decimal("50.00")
#: A charge is out of the ordinary from one and a half times the median of the same charge on the
#: same route, and at least a hundred euros above it — measured on at least four other containers
#: of the last twelve months, since a median of three is not a norm.
OUTLIER_RATIO = Decimal("1.5")
OUTLIER_MIN_EXCESS = Decimal("100.00")
OUTLIER_MIN_BASIS = 4
OUTLIER_LOOKBACK = timedelta(days=365)
#: Charges that follow the value of the goods, not the route: a box of tyres and a box of engines
#: pay very different duty on the same voyage, and the route's median says nothing about either.
VALUE_BASED = {"CUSTOMS_DUTY", "IMPORT_VAT", "INSURANCE"}
#: A forwarder invoices within the month. An estimate still standing two months after the goods
#: landed is an invoice nobody chased, or a cost that was never billed and inflates the landed cost.
ESTIMATE_STALE_AFTER = timedelta(days=60)

#: The findings a claim can be made about. The others are about the quality of the figures.
RECOVERABLE = ("DUPLICATE_CHARGE", "ABOVE_QUOTE", "OUTLIER_CHARGE")


@dataclass
class Finding:
    code: str
    confidence: Confidence
    amount: Decimal
    container_id: UUID | None
    container_number: str | None
    cost_type: str | None
    vendor: str | None
    invoice_number: str | None
    cost_ids: list[UUID]
    #: How many containers the rule compared with (statistical rules only).
    basis: int | None = None
    #: The moving parts of the rule, as raw strings, for the sentence the screen writes.
    params: dict[str, str] = field(default_factory=dict)


@dataclass
class Margin:
    sku: str
    description: str | None
    quantity: Decimal
    unit_fob: Decimal
    unit_landed: Decimal
    #: Purchase-to-landed, in euros over the period's volume: what a price set on the purchase price
    #: overstates the margin by. Present with or without a selling price.
    approach_costs: Decimal
    sale_price: Decimal | None = None
    margin_on_fob_pct: Decimal | None = None
    margin_real_pct: Decimal | None = None
    points_lost: Decimal | None = None


@dataclass
class DemurrageLine:
    container_id: UUID
    container_number: str
    paid: Decimal
    avoided: Decimal | None
    quantity: Decimal
    #: What the demurrage added to every unit that was in the box.
    per_unit: Decimal | None
    rule: str


@dataclass
class CoefficientBucket:
    key: str
    label: str
    fob: Decimal
    landed: Decimal
    coefficient: Decimal | None


@dataclass
class Completeness:
    containers: int
    fob: Decimal
    landed: Decimal
    #: Part of the landed cost that still rests on estimates rather than invoices.
    estimated: Decimal
    estimated_share_pct: Decimal | None
    invoices_to_review: int
    containers_without_cost: int
    #: Where the exchange rates of the period's costs came from: ecb, ecb_latest, manual, same.
    fx_sources: dict[str, int]


@dataclass
class Headline:
    #: Margin overstated by pricing on the purchase price, over the priced articles of the period.
    margin_overstated: Decimal
    priced_skus: int
    unpriced_skus: int
    #: What the sure findings a claim can be made about add up to, and what the doubtful ones do.
    recoverable_sure: Decimal
    recoverable_to_check: Decimal
    demurrage_paid: Decimal


@dataclass
class Audit:
    base_currency: str
    period_from: date
    period_to: date
    headline: Headline
    margins: list[Margin]
    findings: list[Finding]
    demurrage: list[DemurrageLine]
    coefficient_by_month: list[CoefficientBucket]
    coefficient_by_supplier: list[CoefficientBucket]
    coefficient: Decimal | None
    assumed_coefficient: Decimal | None
    completeness: Completeness


def audit_report(
    db: Session, comp: Computation, org: Organization, period_from: date, period_to: date
) -> Audit:
    every = {row.container_id: row.container for row in comp.load_rows.values()}
    boxes = _period_containers(comp, period_from, period_to)
    costs_in = _costs_of(comp, boxes)
    quantities = _quantities(comp, boxes)

    margins = _margins(db, comp, org, period_from, period_to)
    # One euro, one finding: what the sure rules have already found is taken out of the charges
    # before the statistical rule looks at them, or a duplicate would come back as "far above the
    # route" and an invoice above its quote would be claimed twice.
    sure = _duplicates(comp, every, boxes, costs_in) + _above_quote(comp, every, costs_in)
    findings = (
        sure
        + _outliers(comp, every, boxes, period_to, _claimed(sure))
        + _stale_estimates(comp, every, boxes, period_to)
        + _unallocated(comp, every, costs_in)
        + _duty_without_rate(comp, every, costs_in)
    )
    findings.sort(key=lambda f: (f.confidence != "sure", -f.amount, f.code))
    demurrage = _demurrage(db, org, period_from, period_to, quantities)
    monthly = landed_cost_report(comp, org, group_by="month", period_from=period_from, period_to=period_to)
    by_supplier = landed_cost_report(
        comp, org, group_by="supplier", period_from=period_from, period_to=period_to
    )

    priced = [m for m in margins if m.sale_price is not None]
    return Audit(
        base_currency=org.base_currency,
        period_from=period_from,
        period_to=period_to,
        headline=Headline(
            margin_overstated=q2(sum((m.approach_costs for m in priced), ZERO)),
            priced_skus=len(priced),
            unpriced_skus=len(margins) - len(priced),
            recoverable_sure=q2(
                sum((f.amount for f in findings if f.code in RECOVERABLE and f.confidence == "sure"), ZERO)
            ),
            recoverable_to_check=q2(
                sum(
                    (f.amount for f in findings if f.code in RECOVERABLE and f.confidence == "to_check"), ZERO
                )
            ),
            demurrage_paid=q2(sum((line.paid for line in demurrage), ZERO)),
        ),
        margins=margins,
        findings=findings,
        demurrage=demurrage,
        coefficient_by_month=[_coefficient(b) for b in monthly.buckets],
        coefficient_by_supplier=[_coefficient(b) for b in by_supplier.buckets],
        coefficient=q4(monthly.totals.landed / monthly.totals.fob) if monthly.totals.fob else None,
        assumed_coefficient=_assumed(org),
        completeness=_completeness(db, comp, org, boxes, costs_in, monthly.totals.fob, monthly.totals.landed),
    )


# ------------------------------------------------------------------------------- what is in the period


def _period_containers(comp: Computation, period_from: date, period_to: date) -> dict[UUID, Container]:
    found: dict[UUID, Container] = {}
    for load in comp.loads:
        container = comp.load_rows[load.id].container
        landed_on = arrival_date(container)
        if landed_on is not None and period_from <= landed_on <= period_to:
            found[container.id] = container
    return found


def _costs_of(comp: Computation, boxes: dict[UUID, Container]) -> dict[UUID, Cost]:
    """The live costs of the period: those whose allocation lands on a container that arrived in it,
    plus those attached to such a container that the engine could not place."""
    found: dict[UUID, Cost] = {}
    for allocation in comp.result.allocations:
        if comp.load_rows[allocation.load_id].container_id in boxes:
            found[allocation.cost_id] = comp.cost_rows[allocation.cost_id]
    for cost in comp.cost_rows.values():
        if cost.container_id in boxes:
            found[cost.id] = cost
    return found


def _quantities(comp: Computation, boxes: dict[UUID, Container]) -> dict[UUID, Decimal]:
    per_box: dict[UUID, Decimal] = defaultdict(Decimal)
    for load in comp.loads:
        if load.container_id in boxes:
            per_box[load.container_id] += load.quantity
    return per_box


def _number(comp: Computation, every: dict[UUID, Container], cost: Cost) -> tuple[UUID | None, str | None]:
    """The container a cost is about: its own, else the one its allocation lands on when there is one."""
    if cost.container_id is not None:
        box = every.get(cost.container_id)
        return cost.container_id, box.container_number if box is not None else None
    landed_on = {
        comp.load_rows[a.load_id].container_id for a in comp.result.allocations if a.cost_id == cost.id
    }
    if len(landed_on) == 1:
        (container_id,) = landed_on
        return container_id, every[container_id].container_number
    return None, None


def _finding(
    comp: Computation,
    every: dict[UUID, Container],
    code: str,
    confidence: Confidence,
    amount: Decimal,
    cost: Cost,
    **params: str,
) -> Finding:
    container_id, number = _number(comp, every, cost)
    return Finding(
        code=code,
        confidence=confidence,
        amount=q2(amount),
        container_id=container_id,
        container_number=number,
        cost_type=cost.cost_type.value,
        vendor=cost.vendor,
        invoice_number=cost.invoice_number,
        cost_ids=[cost.id],
        params=params,
    )


# ------------------------------------------------------------------------------- the rules


def _duplicates(
    comp: Computation, every: dict[UUID, Container], boxes: dict[UUID, Container], costs_in: dict[UUID, Cost]
) -> list[Finding]:
    """The same charge on the same container from two invoices, this close in amount."""
    groups: dict[tuple[UUID, str], list[Cost]] = defaultdict(list)
    for cost in costs_in.values():
        if (
            cost.status is CostStatus.ACTUAL
            and cost.container_id in boxes
            and cost.cost_type.value not in EXCLUDED_FROM_LANDED
        ):
            groups[(cost.container_id, cost.cost_type.value)].append(cost)
    found: list[Finding] = []
    for (container_id, _), costs in groups.items():
        costs.sort(key=lambda c: (c.cost_date, c.created_at))
        for i, first in enumerate(costs):
            for second in costs[i + 1 :]:
                if (first.vendor, first.invoice_number) == (second.vendor, second.invoice_number):
                    continue  # two lines of one invoice are that invoice's business
                larger = max(first.amount_base, second.amount_base)
                if larger == 0 or abs(first.amount_base - second.amount_base) > larger * DUPLICATE_TOLERANCE:
                    continue
                finding = _finding(
                    comp,
                    every,
                    "DUPLICATE_CHARGE",
                    "sure",
                    min(first.amount_base, second.amount_base),
                    second,
                    first_invoice=first.invoice_number or "",
                    first_vendor=first.vendor or "",
                    first_amount=f"{first.amount_base:.2f}",
                )
                finding.container_number = boxes[container_id].container_number
                finding.cost_ids = [first.id, second.id]
                found.append(finding)
    return found


def _above_quote(
    comp: Computation, every: dict[UUID, Container], costs_in: dict[UUID, Cost]
) -> list[Finding]:
    """An invoice above the quote it replaced: the estimate is the forwarder's own figure."""
    found: list[Finding] = []
    for actual, estimate in comp.superseded:
        if actual.id not in costs_in or actual.cost_type.value in EXCLUDED_FROM_LANDED:
            continue
        excess = actual.amount_base - estimate.amount_base
        if estimate.amount_base <= 0 or excess < ABOVE_QUOTE_MIN_AMOUNT:
            continue
        if excess < estimate.amount_base * ABOVE_QUOTE_MIN_SHARE:
            continue
        found.append(
            _finding(
                comp,
                every,
                "ABOVE_QUOTE",
                "sure",
                excess,
                actual,
                quoted=f"{estimate.amount_base:.2f}",
                invoiced=f"{actual.amount_base:.2f}",
                share_pct=f"{(excess / estimate.amount_base * 100).quantize(Decimal('0.1'))}",
            )
        )
    return found


def _claimed(findings: list[Finding]) -> dict[tuple[UUID, str], Decimal]:
    """What the sure findings already account for, per container and type of charge."""
    claimed: dict[tuple[UUID, str], Decimal] = defaultdict(Decimal)
    for finding in findings:
        if finding.container_id is not None and finding.cost_type is not None:
            claimed[(finding.container_id, finding.cost_type)] += finding.amount
    return claimed


def _outliers(
    comp: Computation,
    every: dict[UUID, Container],
    boxes: dict[UUID, Container],
    period_to: date,
    claimed: dict[tuple[UUID, str], Decimal],
) -> list[Finding]:
    """A charge far above the same charge on the same route, over the last twelve months.

    Compared per container (the charges of one type on one box are added up, less what a sure
    finding already claims) and only when there are enough other boxes to call the middle of them a
    norm. What comes out is a question — the box may have been heavier, the route congested — and
    the finding says so.
    """
    since = period_to - OUTLIER_LOOKBACK
    per_box_type: dict[tuple[UUID, str], Decimal] = defaultdict(Decimal)
    route_of: dict[UUID, str] = {}
    number_of: dict[UUID, str] = {}
    for cost in comp.cost_rows.values():
        if cost.status is not CostStatus.ACTUAL or cost.container_id is None:
            continue
        if cost.cost_type.value in EXCLUDED_FROM_LANDED or cost.cost_type.value in VALUE_BASED:
            continue
        container = every.get(cost.container_id)
        if container is None:
            continue
        landed_on = arrival_date(container)
        if landed_on is None or not (since <= landed_on <= period_to):
            continue
        per_box_type[(cost.container_id, cost.cost_type.value)] += cost.amount_base
        route_of[cost.container_id] = _route(container)[0]
        number_of[cost.container_id] = container.container_number
    for key in per_box_type:
        per_box_type[key] -= claimed.get(key, ZERO)

    found: list[Finding] = []
    for (container_id, cost_type), amount in per_box_type.items():
        if container_id not in boxes:
            continue
        peers = [
            other
            for (other_id, other_type), other in per_box_type.items()
            if other_type == cost_type
            and other_id != container_id
            and route_of[other_id] == route_of[container_id]
        ]
        if len(peers) < OUTLIER_MIN_BASIS:
            continue
        norm = Decimal(median(peers))
        excess = amount - norm
        if amount <= norm * OUTLIER_RATIO or excess < OUTLIER_MIN_EXCESS:
            continue
        # The invoices behind the sum, the largest first: that is the one the question is about.
        costs = sorted(
            (
                c
                for c in comp.cost_rows.values()
                if c.container_id == container_id
                and c.cost_type.value == cost_type
                and c.status is CostStatus.ACTUAL
            ),
            key=lambda c: -c.amount_base,
        )
        found.append(
            Finding(
                code="OUTLIER_CHARGE",
                confidence="to_check",
                amount=q2(excess),
                container_id=container_id,
                container_number=number_of[container_id],
                cost_type=cost_type,
                vendor=costs[0].vendor if costs else None,
                invoice_number=costs[0].invoice_number if costs else None,
                cost_ids=[c.id for c in costs],
                basis=len(peers),
                params={
                    "amount": f"{amount:.2f}",
                    "median": f"{q2(norm):.2f}",
                    "ratio": f"{(amount / norm).quantize(Decimal('0.1'))}",
                    "route": route_of[container_id],
                },
            )
        )
    return found


def _stale_estimates(
    comp: Computation, every: dict[UUID, Container], boxes: dict[UUID, Container], period_to: date
) -> list[Finding]:
    found: list[Finding] = []
    for cost in comp.cost_rows.values():
        if cost.status is not CostStatus.ESTIMATE or cost.container_id not in boxes:
            continue
        landed_on = arrival_date(boxes[cost.container_id])
        if landed_on is None or period_to - landed_on < ESTIMATE_STALE_AFTER:
            continue
        found.append(
            _finding(
                comp,
                every,
                "ESTIMATE_NEVER_INVOICED",
                "sure",
                cost.amount_base,
                cost,
                days=str((period_to - landed_on).days),
                landed_on=landed_on.isoformat(),
            )
        )
    return found


def _unallocated(
    comp: Computation, every: dict[UUID, Container], costs_in: dict[UUID, Cost]
) -> list[Finding]:
    found: list[Finding] = []
    for missing in comp.result.unallocated:
        cost = costs_in.get(missing.cost_id)
        if cost is None:
            continue
        found.append(
            _finding(comp, every, "UNALLOCATED_COST", "sure", cost.amount_base, cost, reason=missing.code)
        )
    return found


def _duty_without_rate(
    comp: Computation, every: dict[UUID, Container], costs_in: dict[UUID, Cost]
) -> list[Finding]:
    found: list[Finding] = []
    for note in comp.result.notes:
        cost = costs_in.get(note.cost_id)
        if cost is None or note.code != "DUTY_RATE_PARTIAL":
            continue
        found.append(
            _finding(
                comp,
                every,
                "DUTY_RATE_MISSING",
                "sure",
                cost.amount_base,
                cost,
                lines=str(len(note.load_ids)),
            )
        )
    return found


# ------------------------------------------------------------------------------- the other sections


def _margins(
    db: Session, comp: Computation, org: Organization, period_from: date, period_to: date
) -> list[Margin]:
    articles: list[SkuSummary] = sku_report(db, comp, org, period_from=period_from, period_to=period_to)
    found: list[Margin] = []
    for article in articles:
        margin = Margin(
            sku=article.sku,
            description=article.description,
            quantity=article.quantity,
            unit_fob=article.unit_fob,
            unit_landed=article.unit_landed,
            approach_costs=q2(article.landed - article.fob),
        )
        price = article.sale_price
        # A price in another currency than the books gives no margin here either (see sku_report).
        if price is not None and article.margin_unit is not None and price > 0:
            margin.sale_price = price
            margin.margin_on_fob_pct = ((price - article.unit_fob) / price * 100).quantize(Decimal("0.1"))
            margin.margin_real_pct = ((price - article.unit_landed) / price * 100).quantize(Decimal("0.1"))
            margin.points_lost = (margin.margin_on_fob_pct - margin.margin_real_pct).quantize(Decimal("0.1"))
        found.append(margin)
    found.sort(key=lambda m: -m.approach_costs)
    return found


def _demurrage(
    db: Session, org: Organization, period_from: date, period_to: date, quantities: dict[UUID, Decimal]
) -> list[DemurrageLine]:
    report = dnd_report(
        db, org, period_from=period_from, period_to=period_to, daily_rate=_daily_rate(db, org)
    )
    lines: list[DemurrageLine] = []
    for line in report.lines:
        quantity = quantities.get(line.container_id, Decimal(0))
        lines.append(
            DemurrageLine(
                container_id=line.container_id,
                container_number=line.container_number,
                paid=line.paid,
                avoided=line.avoided,
                quantity=quantity,
                per_unit=q4(line.paid / quantity) if quantity and line.paid else None,
                rule=line.rule,
            )
        )
    return lines


def _daily_rate(db: Session, org: Organization) -> Decimal | None:
    from app.domain.models import CostType, RateBasis, RateCard

    card = db.scalar(
        select(RateCard).where(
            RateCard.org_id == org.id,
            RateCard.cost_type == CostType.DEMURRAGE,
            RateCard.basis == RateBasis.FLAT,
        )
    )
    return card.amount if card is not None else None


def _coefficient(bucket: Bucket) -> CoefficientBucket:
    return CoefficientBucket(
        key=bucket.key,
        label=bucket.label,
        fob=bucket.fob,
        landed=bucket.landed,
        coefficient=q4(bucket.landed / bucket.fob) if bucket.fob else None,
    )


def _assumed(org: Organization) -> Decimal | None:
    raw = (org.settings or {}).get("assumed_coefficient")
    try:
        return q4(Decimal(str(raw))) if raw is not None else None
    except ArithmeticError:
        return None


def _completeness(
    db: Session,
    comp: Computation,
    org: Organization,
    boxes: dict[UUID, Container],
    costs_in: dict[UUID, Cost],
    fob: Decimal,
    landed: Decimal,
) -> Completeness:
    estimated = ZERO
    for allocation in comp.result.allocations:
        cost = comp.cost_rows[allocation.cost_id]
        in_period = comp.load_rows[allocation.load_id].container_id in boxes
        counted = cost.cost_type.value not in EXCLUDED_FROM_LANDED
        if cost.status is CostStatus.ESTIMATE and in_period and counted:
            estimated += allocation.amount_base
    costed = {comp.load_rows[a.load_id].container_id for a in comp.result.allocations}
    to_review = db.scalar(
        select(func.count(Invoice.id)).where(
            Invoice.org_id == org.id, Invoice.status == InvoiceStatus.NEEDS_REVIEW
        )
    )
    return Completeness(
        containers=len(boxes),
        fob=fob,
        landed=landed,
        estimated=q2(estimated),
        estimated_share_pct=(estimated / landed * 100).quantize(Decimal("0.1")) if landed else None,
        invoices_to_review=int(to_review or 0),
        containers_without_cost=sum(1 for c in boxes if c not in costed),
        fx_sources=dict(Counter(cost.fx_source for cost in costs_in.values())),
    )
