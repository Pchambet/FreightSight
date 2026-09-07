"""Landed cost allocation engine, Phase 0.

Pure functions only: no I/O, no ORM. Decimal everywhere, ROUND_HALF_UP, largest-remainder split so the
allocated parts always sum to the cost being allocated, to the cent.

Phase 0 scope: one container, its linked purchase orders, one total of additional costs. Allocation is
BY_VALUE (pro rata of PO value) unless every link carries a legacy percentage and those sum to exactly
100.00, in which case the percentages are honoured (MANUAL). Anything else is reported, never guessed.
"""

from __future__ import annotations

from collections.abc import Hashable, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import TypeVar

CENT = Decimal("0.01")
HUNDRED = Decimal("100.00")

K = TypeVar("K", bound=Hashable)


class AllocationMethod(StrEnum):
    BY_VALUE = "BY_VALUE"
    MANUAL = "MANUAL"


class AllocationError(ValueError):
    pass


def quantize_cent(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def split_largest_remainder[K: Hashable](
    amount: Decimal, weights: dict[K, Decimal], order: Sequence[K]
) -> dict[K, Decimal]:
    """Split `amount` proportionally to `weights`. Guarantees sum(result) == amount (2 dp).

    `order` fixes the tie-break when several keys have the same fractional remainder, so the result is
    deterministic across runs.
    """
    if amount != quantize_cent(amount):
        raise AllocationError(f"amount must have at most 2 decimals, got {amount}")
    if any(w < 0 for w in weights.values()):
        raise AllocationError("weights must be >= 0")
    total_weight = sum(weights.values(), Decimal(0))
    if total_weight <= 0:
        raise AllocationError("sum of weights must be > 0")

    raw = {k: amount * weights[k] / total_weight for k in order}
    floored = {k: raw[k].quantize(CENT, rounding=ROUND_DOWN) for k in order}
    remainder = amount - sum(floored.values(), Decimal(0))
    n_cents = int((remainder / CENT).to_integral_value())
    position = {k: i for i, k in enumerate(order)}
    ranked = sorted(order, key=lambda k: (-(raw[k] - floored[k]), position[k]))
    for k in ranked[:n_cents]:
        floored[k] += CENT
    assert sum(floored.values(), Decimal(0)) == amount
    return floored


@dataclass(frozen=True)
class LinkInput:
    key: str  # PO id as string, used as the stable identity
    po_number: str
    fob_value: Decimal
    allocation_pct: Decimal | None = None


@dataclass(frozen=True)
class Warning_:
    code: str
    message: str


@dataclass
class AllocationOutcome:
    method: AllocationMethod | None
    parts: dict[str, Decimal] = field(default_factory=dict)  # key -> allocated amount
    unallocated: Decimal = Decimal("0.00")
    warnings: list[Warning_] = field(default_factory=list)


def allocate_container(total: Decimal, links: Sequence[LinkInput]) -> AllocationOutcome:
    """Allocate `total` across `links` for one container.

    Never raises for data problems: they land in `warnings` and `unallocated`.
    """
    total = quantize_cent(total)
    ordered = sorted(links, key=lambda lk: (lk.po_number, lk.key))
    order = [lk.key for lk in ordered]

    if not ordered:
        return AllocationOutcome(
            method=None,
            unallocated=total,
            warnings=[Warning_("NO_TARGET", "No purchase order is linked to this container.")],
        )

    pcts = [lk.allocation_pct for lk in ordered]
    warnings: list[Warning_] = []

    if all(p is not None for p in pcts):
        pct_sum = sum((p for p in pcts if p is not None), Decimal(0))
        if pct_sum == HUNDRED:
            weights = {lk.key: lk.allocation_pct or Decimal(0) for lk in ordered}
            return AllocationOutcome(
                method=AllocationMethod.MANUAL,
                parts=split_largest_remainder(total, weights, order),
            )
        warnings.append(
            Warning_(
                "DEPRECATED_ALLOCATION_PCT",
                f"Legacy allocation percentages sum to {pct_sum:.2f}, expected 100.00. "
                "Falling back to allocation by PO value.",
            )
        )
    elif any(p is not None for p in pcts):
        warnings.append(
            Warning_(
                "DEPRECATED_ALLOCATION_PCT",
                "Legacy allocation percentages are missing on some purchase orders. "
                "Falling back to allocation by PO value.",
            )
        )

    weights = {lk.key: lk.fob_value for lk in ordered}
    if sum(weights.values(), Decimal(0)) <= 0:
        warnings.append(
            Warning_(
                "ALL_WEIGHTS_ZERO",
                "Every linked purchase order has a zero value; nothing can be allocated by value.",
            )
        )
        return AllocationOutcome(method=AllocationMethod.BY_VALUE, unallocated=total, warnings=warnings)

    return AllocationOutcome(
        method=AllocationMethod.BY_VALUE,
        parts=split_largest_remainder(total, weights, order),
        warnings=warnings,
    )
