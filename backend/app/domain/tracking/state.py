"""Pure derivation: from a container's event history to its state. No database, no clock of its own.

Two axes, deliberately separate:
  * `milestone`  — where the box is, from the events (this module);
  * `tracking_state` — the health of the subscription (set by the ingestion service).

Demurrage is the money question: `last_free_day = discharged_at + free_days - 1` in calendar days, as
soon as a real (non-estimated) DISCHARGED exists, and the risk band is recomputed from it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.domain.models import Container, ContainerMilestone, DndRisk, MilestoneCode, Organization
from app.domain.tracking.ports import CONTAINER_MILESTONE, ORDER, ProviderEvent

#: An ETA that moves by less than this is noise; past `ETA_WARNING_HOURS` it is a warning.
DEFAULT_DEMURRAGE_DAYS = 5
DEFAULT_DETENTION_DAYS = 7

ETA_SHIFT_HOURS = 12
ETA_WARNING_HOURS = 48


@dataclass(frozen=True)
class ContainerSnapshot:
    milestone: ContainerMilestone
    eta: datetime | None
    ata: datetime | None
    discharged_at: datetime | None
    gate_out_at: datetime | None
    empty_returned_at: datetime | None


def _first_actual(events: Sequence[ProviderEvent], code: MilestoneCode) -> datetime | None:
    times = [e.occurred_at for e in events if e.code == code]
    return min(times) if times else None


def derive(events: Sequence[ProviderEvent], now: datetime | None = None) -> ContainerSnapshot:
    """Milestone and timestamps from the events. Estimates never move the milestone, and neither does
    an actual event dated in the future — carriers do publish those."""
    moment = now or datetime.now(UTC)
    actual = [e for e in events if not e.is_estimate and e.occurred_at <= moment]
    ranked = [e.code for e in actual if e.code in ORDER]
    milestone = ContainerMilestone.BOOKED
    for code in sorted(ranked, key=ORDER.index):
        milestone = CONTAINER_MILESTONE.get(code, milestone)
    estimates = sorted(
        (e for e in events if e.is_estimate and e.code == MilestoneCode.VESSEL_ARRIVED),
        key=lambda e: e.occurred_at,
    )
    return ContainerSnapshot(
        milestone=milestone,
        eta=estimates[-1].occurred_at if estimates else None,
        ata=_first_actual(actual, MilestoneCode.VESSEL_ARRIVED),
        discharged_at=_first_actual(actual, MilestoneCode.DISCHARGED),
        gate_out_at=_first_actual(actual, MilestoneCode.GATE_OUT_FULL),
        empty_returned_at=_first_actual(actual, MilestoneCode.GATE_IN_EMPTY_RETURN),
    )


def free_days_for(container: Container, org: Organization, *, detention: bool = False) -> int:
    """Free days: the container's own value, else the org's per-carrier setting, else the org default.

    The exact counting rule differs by terminal and by carrier, so it is a setting, never a guess.
    `detention` asks for the empty-return clock rather than the terminal one.
    """
    own = container.free_days_detention if detention else container.free_days_demurrage
    if own is not None:
        return own
    key = "free_days_detention" if detention else "free_days"
    per_carrier = org.settings.get(key) if isinstance(org.settings, dict) else None
    if isinstance(per_carrier, dict) and container.carrier_scac:
        value = per_carrier.get(container.carrier_scac)
        if isinstance(value, int):
            return value
    # The column defaults, repeated for an organization that has not been through the database yet.
    fallback = DEFAULT_DETENTION_DAYS if detention else DEFAULT_DEMURRAGE_DAYS
    org_value = org.free_days_detention if detention else org.free_days_demurrage
    return org_value if org_value is not None else fallback


def risk_band(days_left: int) -> DndRisk:
    if days_left < 0:
        return DndRisk.INCURRING
    if days_left <= 1:
        return DndRisk.HIGH
    if days_left <= 3:
        return DndRisk.MEDIUM
    return DndRisk.LOW


def derive_dnd(container: Container, org: Organization, now: datetime | None = None) -> None:
    """Set `last_free_day`, `detention_deadline` and `dnd_risk` in place. Calendar days.

    Two clocks, one after the other: demurrage runs at the terminal from discharge until the box is
    picked up, then detention runs from pickup until the empty is back. The risk shown is whichever
    one is running now — there is only ever one, and it is the one costing money today.
    """
    moment = now or datetime.now(UTC)
    demurrage_days = free_days_for(container, org)
    detention_days = free_days_for(container, org, detention=True)

    container.last_free_day = (
        (container.discharged_at.date() + timedelta(days=demurrage_days - 1))
        if container.discharged_at
        else None
    )
    container.detention_deadline = (
        (container.gate_out_at.date() + timedelta(days=detention_days - 1)) if container.gate_out_at else None
    )

    if container.empty_returned_at is not None:
        container.dnd_risk = DndRisk.NONE  # the box is back: both clocks have stopped
    elif container.gate_out_at is not None and container.detention_deadline is not None:
        container.dnd_risk = risk_band((container.detention_deadline - moment.date()).days)
    elif container.discharged_at is not None and container.last_free_day is not None:
        container.dnd_risk = risk_band((container.last_free_day - moment.date()).days)
    else:
        container.dnd_risk = DndRisk.NONE  # not landed yet: nothing is running


def apply_snapshot(container: Container, snapshot: ContainerSnapshot) -> None:
    """Move the container forward. Timestamps already known are kept: the first actual wins, and a
    provider that stops reporting a milestone never erases it."""
    if ORDER.index(MilestoneCode(snapshot.milestone.value)) >= ORDER.index(
        MilestoneCode(container.milestone.value)
    ):
        container.milestone = snapshot.milestone
    for field_name in ("ata", "discharged_at", "gate_out_at", "empty_returned_at"):
        value = getattr(snapshot, field_name)
        if value is not None:
            setattr(container, field_name, value)


def eta_shift(previous: datetime | None, new: datetime | None) -> tuple[Decimal, str] | None:
    """`(delta_hours, severity)` when an ETA *move* is worth recording, else None. Decimal, never float.

    A first ETA is not a change: it is recorded on the container, not in the history."""
    if new is None or previous is None:
        return None
    seconds = Decimal(int((new - previous).total_seconds()))
    hours = (seconds / Decimal(3600)).quantize(Decimal("0.1"))
    if abs(hours) < Decimal(ETA_SHIFT_HOURS):
        return None
    return (hours, "warning" if abs(hours) > Decimal(ETA_WARNING_HOURS) else "info")
