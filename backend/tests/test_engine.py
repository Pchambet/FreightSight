"""Reference cases T1-T9 from docs/plan/01_backend.md, executed against the pure engine."""

from __future__ import annotations

import random
from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.domain.costing.engine import (
    AllocationError,
    AllocationResult,
    Cost,
    Load,
    ManualSplit,
    allocate,
    split_largest_remainder,
)

D = Decimal


def load(
    container: str,
    po: str,
    line_no: int,
    qty: str,
    price: str,
    *,
    kg: str | None = None,
    cbm: str | None = None,
    duty: str | None = None,
    container_id: UUID | None = None,
    shipment_id: UUID | None = None,
    po_id: UUID | None = None,
    line_id: UUID | None = None,
) -> Load:
    return Load(
        id=line_id or uuid4(),
        container_id=container_id or uuid4(),
        shipment_id=shipment_id,
        po_id=po_id or uuid4(),
        po_line_id=uuid4(),
        quantity=D(qty),
        unit_price_base=D(price),
        unit_weight_kg=None if kg is None else D(kg),
        unit_volume_cbm=None if cbm is None else D(cbm),
        duty_rate=None if duty is None else D(duty),
        sort_key=(container, po, line_no),
    )


def cost(
    scope: str,
    target: UUID,
    amount: str,
    ctype: str = "DRAYAGE",
    method: str = "BY_VALUE",
    splits: Sequence[ManualSplit] = (),
) -> Cost:
    return Cost(uuid4(), scope, target, ctype, D(amount), method, tuple(splits))


def parts(result: AllocationResult, cost_id: UUID) -> list[Decimal]:
    return [a.amount_base for a in result.allocations if a.cost_id == cost_id]


def test_t1_by_value_reconciles_to_cent() -> None:
    cnt = uuid4()
    a = load("CNT1", "PO-A", 1, "1", "12500.50", container_id=cnt)
    b = load("CNT1", "PO-B", 1, "1", "8400.00", container_id=cnt)
    c = cost("CONTAINER", cnt, "1000.00")
    r = allocate([c], [a, b])
    assert parts(r, c.id) == [D("598.10"), D("401.90")]
    assert r.unallocated == []


def test_t2_quantity_tie_break_deterministic() -> None:
    cnt = uuid4()
    loads = [load("CNT1", f"PO-{i}", 1, "10", "1", container_id=cnt) for i in range(3)]
    c = cost("CONTAINER", cnt, "100.00", method="BY_QUANTITY")
    for _ in range(5):
        r = allocate([c], loads)
        assert parts(r, c.id) == [D("33.34"), D("33.33"), D("33.33")]


def test_t3_multicurrency_weight() -> None:
    cnt = uuid4()
    a = load("CNT1", "PO-A", 1, "600", "10", kg="2", container_id=cnt)
    b = load("CNT1", "PO-B", 1, "400", "10", kg="2", container_id=cnt)
    # 2000.00 EUR at 1.0850 -> 2170.00 USD base, done by the service; the engine sees amount_base
    c = cost("CONTAINER", cnt, "2170.00", ctype="OCEAN_FREIGHT", method="BY_WEIGHT")
    r = allocate([c], [a, b])
    assert parts(r, c.id) == [D("1302.00"), D("868.00")]


def test_t4_duty_theoretical_vs_cif() -> None:
    cnt, po = uuid4(), uuid4()
    l1 = load("CNT1", "PO-1", 1, "1000", "10.00", duty="0.045", container_id=cnt, po_id=po)
    l2 = load("CNT1", "PO-1", 2, "100", "50.00", duty="0", container_id=cnt, po_id=po)
    freight = cost("CONTAINER", cnt, "1500.00", ctype="OCEAN_FREIGHT")
    insurance = cost("CONTAINER", cnt, "150.00", ctype="INSURANCE")
    duty_theo = cost("PO", po, "499.50", ctype="CUSTOMS_DUTY", method="BY_THEORETICAL_DUTY")
    r = allocate([freight, insurance, duty_theo], [l1, l2])
    assert parts(r, freight.id) == [D("1000.00"), D("500.00")]
    assert parts(r, insurance.id) == [D("100.00"), D("50.00")]
    assert r.cif[l1.id] == D("11100.00") and r.cif[l2.id] == D("5550.00")
    assert parts(r, duty_theo.id) == [D("499.50")]  # l2 gets 0 and is omitted

    duty_cif = cost("PO", po, "499.50", ctype="CUSTOMS_DUTY", method="BY_CIF_VALUE")
    r2 = allocate([freight, insurance, duty_cif], [l1, l2])
    assert parts(r2, duty_cif.id) == [D("333.00"), D("166.50")]

    vat = cost("PO", po, "3429.90", ctype="IMPORT_VAT")
    r3 = allocate([freight, insurance, duty_theo, vat], [l1, l2])
    assert sum(parts(r3, vat.id)) == D("3429.90")


def test_t5_po_split_across_containers_and_shipment_cost() -> None:
    ship, cnt1, cnt2, po_a, po_b = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    a1 = load("CNT1", "PO-A", 1, "600", "10.00", kg="2", container_id=cnt1, shipment_id=ship, po_id=po_a)
    a2 = load("CNT2", "PO-A", 1, "400", "10.00", kg="2", container_id=cnt2, shipment_id=ship, po_id=po_a)
    b1 = load("CNT1", "PO-B", 1, "500", "20.00", kg="5", container_id=cnt1, shipment_id=ship, po_id=po_b)
    dray1 = cost("CONTAINER", cnt1, "300.00")
    dray2 = cost("CONTAINER", cnt2, "200.00")
    ocean = cost("SHIPMENT", ship, "3000.00", ctype="OCEAN_FREIGHT", method="BY_WEIGHT")
    r = allocate([dray1, dray2, ocean], [a1, a2, b1])
    assert parts(r, dray1.id) == [D("112.50"), D("187.50")]
    assert parts(r, dray2.id) == [D("200.00")]
    assert parts(r, ocean.id) == [
        D("800.00"),
        D("1666.67"),
        D("533.33"),
    ]  # sorted by sort_key: CNT1/A, CNT1/B, CNT2/A
    total = sum(a.amount_base for a in r.allocations)
    assert total == D("3500.00")


def test_t6_manual_split_cascade_and_150pct_rejected() -> None:
    cnt, po_a, po_b = uuid4(), uuid4(), uuid4()
    a1 = load("CNT1", "PO-A", 1, "1", "6000", container_id=cnt, po_id=po_a)
    a2 = load("CNT1", "PO-A", 2, "1", "2000", container_id=cnt, po_id=po_a)
    b1 = load("CNT1", "PO-B", 1, "1", "5000", container_id=cnt, po_id=po_b)
    ok = cost(
        "CONTAINER",
        cnt,
        "1000.00",
        method="MANUAL",
        splits=[ManualSplit("po", po_a, D("70")), ManualSplit("po", po_b, D("30"))],
    )
    r = allocate([ok], [a1, a2, b1])
    assert parts(r, ok.id) == [D("525.00"), D("175.00"), D("300.00")]

    bad = cost(
        "CONTAINER",
        cnt,
        "1000.00",
        method="MANUAL",
        splits=[ManualSplit("po", po_a, D("100")), ManualSplit("po", po_b, D("50"))],
    )
    r2 = allocate([bad], [a1, a2, b1])
    assert parts(r2, bad.id) == []
    assert [u.code for u in r2.unallocated] == ["INVALID_MANUAL_SPLIT"]
    assert "150.00" in r2.unallocated[0].message


def test_t7_missing_basis_no_silent_fallback() -> None:
    cnt = uuid4()
    a = load("CNT1", "PO-A", 1, "10", "1", kg="2", container_id=cnt)
    b = load("CNT1", "PO-B", 1, "10", "1", container_id=cnt)  # no weight
    c = cost("CONTAINER", cnt, "100.00", method="BY_WEIGHT")
    r = allocate([c], [a, b])
    assert r.allocations == []
    assert r.unallocated[0].code == "MISSING_BASIS"
    assert r.unallocated[0].load_ids == (b.id,)


def test_t8_no_loads_under_scope() -> None:
    c = cost("CONTAINER", uuid4(), "400.00")
    r = allocate([c], [])
    assert r.unallocated[0].code == "NO_TARGET"


def test_t9_split_property() -> None:
    rng = random.Random(7)
    for _ in range(2000):
        n = rng.randint(1, 50)
        order = [f"k{i}" for i in range(n)]
        weights = {k: D(rng.randint(1, 100_000)) for k in order}
        amount = (D(rng.randint(1, 10_000_000_00)) / 100).quantize(D("0.01"))
        result = split_largest_remainder(amount, weights, order)
        assert sum(result.values()) == amount
        total_w = sum(weights.values())
        for k in order:
            assert result[k] >= 0
            assert abs(result[k] - amount * weights[k] / total_w) < D("0.01")


def test_split_rejects_bad_input() -> None:
    with pytest.raises(AllocationError):
        split_largest_remainder(D("1.005"), {"a": D(1)}, ["a"])
    with pytest.raises(AllocationError):
        split_largest_remainder(D("1.00"), {"a": D(0)}, ["a"])
