"""Engine tests. Numbers mirror the reference cases in docs/plan/01_backend.md (T1, T2, T6, T8, T9)."""

from __future__ import annotations

import random
from decimal import Decimal

import pytest

from app.costing import (
    AllocationError,
    AllocationMethod,
    LinkInput,
    allocate_container,
    split_largest_remainder,
)

D = Decimal


def link(key: str, fob: str, pct: str | None = None) -> LinkInput:
    return LinkInput(key=key, po_number=key, fob_value=D(fob), allocation_pct=None if pct is None else D(pct))


def test_by_value_reconciles_to_cent_t1() -> None:
    """The repo's own sample data: 1000.00 across 12500.50 and 8400.00. Old code returned 1000 + 500."""
    out = allocate_container(D("1000.00"), [link("PO-1", "12500.50"), link("PO-2", "8400.00")])
    assert out.method is AllocationMethod.BY_VALUE
    assert out.parts == {"PO-1": D("598.10"), "PO-2": D("401.90")}
    assert sum(out.parts.values()) == D("1000.00")
    assert out.unallocated == D("0.00")
    assert out.warnings == []


def test_quantity_tie_break_deterministic_t2() -> None:
    weights = {"a": D(10), "b": D(10), "c": D(10)}
    for _ in range(5):
        parts = split_largest_remainder(D("100.00"), weights, ["a", "b", "c"])
        assert parts == {"a": D("33.34"), "b": D("33.33"), "c": D("33.33")}


def test_manual_pct_honoured_when_sum_is_100() -> None:
    out = allocate_container(D("1000.00"), [link("PO-A", "6000", "70"), link("PO-B", "2000", "30")])
    assert out.method is AllocationMethod.MANUAL
    assert out.parts == {"PO-A": D("700.00"), "PO-B": D("300.00")}


def test_legacy_150pct_falls_back_to_value_with_warning_t6() -> None:
    """Michelin 100 % + Pirelli 50 % (the current test_data.csv) must not allocate 150 %."""
    out = allocate_container(D("1000.00"), [link("PO-1", "12500.50", "100"), link("PO-2", "8400.00", "50")])
    assert out.method is AllocationMethod.BY_VALUE
    assert sum(out.parts.values()) == D("1000.00")
    assert [w.code for w in out.warnings] == ["DEPRECATED_ALLOCATION_PCT"]
    assert "150.00" in out.warnings[0].message


def test_partial_pct_falls_back_to_value() -> None:
    out = allocate_container(D("100.00"), [link("PO-1", "50", "100"), link("PO-2", "50")])
    assert out.method is AllocationMethod.BY_VALUE
    assert out.parts == {"PO-1": D("50.00"), "PO-2": D("50.00")}
    assert out.warnings[0].code == "DEPRECATED_ALLOCATION_PCT"


def test_no_links_goes_to_unallocated_t8() -> None:
    out = allocate_container(D("400.00"), [])
    assert out.method is None
    assert out.parts == {}
    assert out.unallocated == D("400.00")
    assert out.warnings[0].code == "NO_TARGET"


def test_all_zero_values_is_reported_not_guessed() -> None:
    out = allocate_container(D("400.00"), [link("PO-1", "0"), link("PO-2", "0")])
    assert out.parts == {}
    assert out.unallocated == D("400.00")
    assert out.warnings[0].code == "ALL_WEIGHTS_ZERO"


def test_split_rejects_bad_input() -> None:
    with pytest.raises(AllocationError):
        split_largest_remainder(D("1.005"), {"a": D(1)}, ["a"])
    with pytest.raises(AllocationError):
        split_largest_remainder(D("1.00"), {"a": D(0)}, ["a"])
    with pytest.raises(AllocationError):
        split_largest_remainder(D("1.00"), {"a": D(-1), "b": D(2)}, ["a", "b"])


def test_split_property_sum_equals_amount_t9() -> None:
    rng = random.Random(42)
    for _ in range(2000):
        n = rng.randint(1, 50)
        order = [f"k{i}" for i in range(n)]
        weights = {k: D(rng.randint(1, 100_000)) for k in order}
        amount = (D(rng.randint(1, 10_000_000_00)) / 100).quantize(D("0.01"))
        parts = split_largest_remainder(amount, weights, order)
        assert sum(parts.values()) == amount
        assert all(p >= 0 for p in parts.values())
        total_w = sum(weights.values())
        for k in order:
            assert abs(parts[k] - amount * weights[k] / total_w) < D("0.01")
