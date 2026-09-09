"""What the background jobs actually do. Plain functions, so they can be called in a test without a
worker, a queue, or a clock.

Every handler that touches tenant data walks the organizations one at a time and sets the tenant
variable before querying: the worker connects as `freightsight_app` like everything else, so Row
Level Security applies to it too. Nothing here reads across organizations.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.fx_ecb import make_fetcher
from app.core.db import get_sessionmaker
from app.core.settings import get_settings
from app.core.tenancy import set_current_org
from app.domain.alerts.notifier import Notification, Notifier, make_notifier
from app.domain.alerts.service import raise_alert
from app.domain.documents.registry import get_store
from app.domain.fx.service import FxService
from app.domain.invoices import service as invoices_service
from app.domain.invoices.registry import get_extractors
from app.domain.models import (
    Alert,
    AlertKind,
    AlertSeverity,
    Container,
    ContainerMilestone,
    DndRisk,
    EtaHistory,
    Invoice,
    InvoiceStatus,
    Membership,
    Organization,
    TrackingEvent,
    TrackingState,
    TrackingSubscription,
    User,
    WebhookDelivery,
)
from app.domain.tracking.delivery import process_stored_delivery
from app.domain.tracking.ports import ProviderNotConfigured, ProviderUnavailable
from app.domain.tracking.ports import TrackingProvider as _TrackingProvider
from app.domain.tracking.registry import get_provider
from app.domain.tracking.service import ingest, refresh
from app.domain.tracking.state import ETA_SHIFT_HOURS, ETA_WARNING_HOURS, derive_dnd

logger = logging.getLogger(__name__)

#: How a handler gets a provider. A parameter rather than a global, so a test can hand in its own.
ProviderFactory = Callable[[str], _TrackingProvider]

#: How long a subscription may stay silent before we say so.
STALE_AFTER = timedelta(hours=48)
#: How many times a failed delivery is retried before it is left alone.
MAX_DELIVERY_ATTEMPTS = 5
#: The hour, in Europe/Paris, at which the demurrage pass runs.
DAILY_RISK_HOUR = 6
PARIS = "Europe/Paris"

RISK_ORDER = [DndRisk.NONE, DndRisk.LOW, DndRisk.MEDIUM, DndRisk.HIGH, DndRisk.INCURRING]
RISK_SEVERITY = {
    DndRisk.LOW: AlertSeverity.INFO,
    DndRisk.MEDIUM: AlertSeverity.WARNING,
    DndRisk.HIGH: AlertSeverity.CRITICAL,
    DndRisk.INCURRING: AlertSeverity.CRITICAL,
}


@contextmanager
def session() -> Iterator[Session]:
    with get_sessionmaker()() as db:
        yield db


def organizations(db: Session) -> list[Organization]:
    return list(db.scalars(select(Organization).order_by(Organization.created_at)))


@contextmanager
def tenant(db: Session, org: Organization) -> Iterator[Organization]:
    """Work as one organization, then put the connection back the way it was found."""
    set_current_org(db, org.id)
    try:
        yield org
    finally:
        set_current_org(db, None)


# ---------------------------------------------------------------------------- deliveries


def retry_failed_deliveries(
    db: Session,
    *,
    now: datetime | None = None,
    provider_factory: ProviderFactory = get_provider,
) -> int:
    """Re-run the deliveries that failed to process. Returns how many were retried.

    A delivery is stored the moment it is verified, so a bug on our side is recoverable: the raw body
    is still there and this replays it. Deliveries that have already been retried too often are left
    alone rather than hammered.
    """
    moment = now or datetime.now(UTC)
    failed = list(
        db.scalars(
            select(WebhookDelivery)
            .where(WebhookDelivery.status == "failed", WebhookDelivery.signature_ok.is_(True))
            .order_by(WebhookDelivery.received_at)
            .limit(50)
        )
    )
    retried = 0
    for delivery in failed:
        attempts = delivery.attempts
        if attempts >= MAX_DELIVERY_ATTEMPTS:
            continue
        if delivery.processed_at and moment < delivery.processed_at + _backoff(attempts):
            continue  # exponential backoff: 1, 2, 4, 8, 16 minutes
        provider = provider_factory(delivery.provider)
        process_stored_delivery(db, provider, delivery, attempt=attempts + 1, now=moment)
        retried += 1
    return retried


def _backoff(attempts: int) -> timedelta:
    return timedelta(minutes=2**attempts)


# ---------------------------------------------------------------------------- silent subscriptions


def poll_stale_subscriptions(
    db: Session,
    *,
    now: datetime | None = None,
    provider_factory: ProviderFactory = get_provider,
) -> int:
    """Ask the provider directly about containers whose feed has gone quiet, and say so if it stays
    quiet. Returns the number of subscriptions polled."""
    moment = now or datetime.now(UTC)
    polled = 0
    for org in organizations(db):
        with tenant(db, org):
            subscriptions = list(
                db.scalars(
                    select(TrackingSubscription).where(
                        TrackingSubscription.org_id == org.id,
                        TrackingSubscription.ended_at.is_(None),
                        TrackingSubscription.provider != "manual",
                    )
                )
            )
            for subscription in subscriptions:
                last = db.scalar(
                    select(TrackingEvent.inserted_at)
                    .where(TrackingEvent.container_id == subscription.container_id)
                    .order_by(TrackingEvent.inserted_at.desc())
                    .limit(1)
                )
                since = last or subscription.subscribed_at or subscription.created_at
                if since is not None and moment - since < STALE_AFTER:
                    continue
                polled += 1
                container = db.get(Container, subscription.container_id)
                if container is None:  # pragma: no cover - foreign key says otherwise
                    continue
                _poll_one(db, org, subscription, container, moment, provider_factory)
            db.commit()
    return polled


def _poll_one(
    db: Session,
    org: Organization,
    subscription: TrackingSubscription,
    container: Container,
    moment: datetime,
    provider_factory: ProviderFactory,
) -> None:
    ingested = 0
    reason = ""
    if subscription.provider_ref:
        try:
            envelope = provider_factory(subscription.provider).fetch(subscription.provider_ref)
            ingested = ingest(
                db,
                org.id,
                container.id,
                envelope.events,
                provider=subscription.provider,
            )
            if ingested:
                refresh(db, org, container, source=subscription.provider, now=moment)
        except (ProviderNotConfigured, ProviderUnavailable) as exc:
            reason = exc.message
    else:
        reason = "no provider reference: this container is tracked webhook-only"
    if ingested:
        return
    days = (moment - (subscription.subscribed_at or subscription.created_at)).days
    raise_alert(
        db,
        org.id,
        kind=AlertKind.TRACKING_DATA_MISSING,
        severity=AlertSeverity.WARNING,
        title=f"No tracking data for {container.container_number}",
        body=(
            f"{subscription.provider} has sent nothing for at least "
            f"{int(STALE_AFTER.total_seconds() // 3600)} hours"
            + (f" ({reason})" if reason else "")
            + ". Check the container on the carrier's own site."
        ),
        dedup_key=f"tracking-stale:{container.id}:{moment.date().isoformat()}",
        container_id=container.id,
        payload={"provider": subscription.provider, "days_since_subscribed": days},
    )
    subscription.last_error = reason or "no data"
    if subscription.status == "active" and container.tracking_state is TrackingState.ACTIVE:
        container.tracking_state = TrackingState.FAILED
    db.flush()


#: How long a delivered container is still worth paying a provider to watch.
KEEP_TRACKING_AFTER_DELIVERY = timedelta(days=7)

DELIVERED_MILESTONES = (ContainerMilestone.DELIVERED, ContainerMilestone.GATE_IN_EMPTY_RETURN)


def end_delivered_subscriptions(
    db: Session, *, now: datetime | None = None, provider_factory: ProviderFactory = get_provider
) -> int:
    """Stop tracking containers that arrived a week ago. Returns how many were unsubscribed.

    Providers charge per tracked container, and a box that has been returned empty is not going to
    move again. The week of grace is for the late gate-in that arrives after the delivery event.
    """
    moment = now or datetime.now(UTC)
    ended = 0
    for org in organizations(db):
        with tenant(db, org):
            subscriptions = list(
                db.scalars(
                    select(TrackingSubscription).where(
                        TrackingSubscription.org_id == org.id,
                        TrackingSubscription.ended_at.is_(None),
                        TrackingSubscription.provider != "manual",
                    )
                )
            )
            for subscription in subscriptions:
                container = db.get(Container, subscription.container_id)
                if container is None or container.milestone not in DELIVERED_MILESTONES:
                    continue
                settled = container.empty_returned_at or container.gate_out_at
                if settled is None or moment - settled < KEEP_TRACKING_AFTER_DELIVERY:
                    continue
                if subscription.provider_ref:
                    try:
                        provider_factory(subscription.provider).unsubscribe(subscription.provider_ref)
                    except (ProviderNotConfigured, ProviderUnavailable) as exc:
                        # The provider will keep charging until someone sorts it out; that is worth
                        # saying, and worth retrying, so the subscription stays open.
                        logger.warning(
                            "could not unsubscribe container %s: %s", container.container_number, exc
                        )
                        subscription.last_error = exc.message
                        continue
                subscription.ended_at = moment
                subscription.status = "ended"
                container.tracking_state = TrackingState.ENDED
                ended += 1
            db.commit()
    return ended


# ---------------------------------------------------------------------------- demurrage


def recompute_dnd_risk(db: Session, *, now: datetime | None = None) -> int:
    """Recompute every live container's demurrage risk and alert on each new threshold crossed.

    The risk only moves when a day passes, so this is what turns a stale MEDIUM into the HIGH that
    someone needs to act on this morning. Returns the number of containers whose band changed.
    """
    moment = now or datetime.now(UTC)
    changed = 0
    for org in organizations(db):
        with tenant(db, org):
            containers = list(
                db.scalars(
                    select(Container).where(
                        Container.org_id == org.id,
                        Container.archived_at.is_(None),
                        Container.discharged_at.is_not(None),
                        Container.gate_out_at.is_(None),
                    )
                )
            )
            for container in containers:
                before = container.dnd_risk
                derive_dnd(container, org, moment)
                if container.dnd_risk == before:
                    continue
                changed += 1
                if RISK_ORDER.index(container.dnd_risk) <= RISK_ORDER.index(before):
                    continue  # the clock only ever gets worse; a downgrade is not news
                _alert_risk(db, org, container, moment)
            db.commit()
    return changed


def _alert_risk(db: Session, org: Organization, container: Container, moment: datetime) -> None:
    lfd = container.last_free_day
    remaining = (lfd - moment.date()).days if lfd else None
    if container.dnd_risk is DndRisk.INCURRING:
        body = f"The last free day was {lfd}. Demurrage is running."
    else:
        body = f"Last free day {lfd}" + (f", {remaining} day(s) left." if remaining is not None else ".")
    raise_alert(
        db,
        org.id,
        kind=AlertKind.DND_RISK,
        severity=RISK_SEVERITY.get(container.dnd_risk, AlertSeverity.INFO),
        title=f"{container.container_number}: demurrage risk {container.dnd_risk.value}",
        body=body,
        # One alert per threshold per container: crossing back and forth cannot spam.
        dedup_key=f"dnd:{container.id}:{container.dnd_risk.value}",
        container_id=container.id,
        payload={"risk": container.dnd_risk.value, "last_free_day": lfd.isoformat() if lfd else None},
    )


# ---------------------------------------------------------------------------- ETA moves


def alert_on_eta_changes(db: Session, *, now: datetime | None = None, lookback_hours: int = 24) -> int:
    """Turn recent ETA history into alerts. Returns how many alerts were raised.

    The history row is the fact; the alert is the telling of it. Keying the alert on the history row
    means this can run as often as it likes.
    """
    moment = now or datetime.now(UTC)
    since = moment - timedelta(hours=lookback_hours)
    raised = 0
    for org in organizations(db):
        with tenant(db, org):
            rows = list(
                db.scalars(
                    select(EtaHistory)
                    .where(EtaHistory.org_id == org.id, EtaHistory.recorded_at >= since)
                    .order_by(EtaHistory.recorded_at)
                )
            )
            for row in rows:
                container = db.get(Container, row.container_id)
                if container is None:  # pragma: no cover
                    continue
                hours = row.delta_hours
                if abs(hours) < Decimal(ETA_SHIFT_HOURS):  # pragma: no cover - not written below 12 h
                    continue
                direction = "later" if hours > 0 else "earlier"
                alert = raise_alert(
                    db,
                    org.id,
                    kind=AlertKind.ETA_CHANGED,
                    severity=(
                        AlertSeverity.WARNING
                        if abs(hours) > Decimal(ETA_WARNING_HOURS)
                        else AlertSeverity.INFO
                    ),
                    title=f"{container.container_number}: arrival moved {abs(hours)} h {direction}",
                    body=f"New ETA {row.eta:%Y-%m-%d %H:%M} UTC, was {row.previous_eta:%Y-%m-%d %H:%M} UTC."
                    if row.previous_eta
                    else f"New ETA {row.eta:%Y-%m-%d %H:%M} UTC.",
                    dedup_key=f"eta:{row.id}",
                    container_id=container.id,
                    payload={"delta_hours": str(hours), "eta": row.eta.isoformat()},
                )
                raised += 1 if alert is not None else 0
            db.commit()
    return raised


# ---------------------------------------------------------------------------- invoice extraction


def extract_invoice(db: Session, org_id: UUID, invoice_id: UUID) -> str:
    """Read one uploaded invoice. Returns the status it ended in.

    Reading is the slow, failure-prone part — a PDF library, sometimes a model over the network — so
    it happens here rather than in the request. Nothing it produces is a cost: the invoice comes out
    in NEEDS_REVIEW, waiting for a person, or in FAILED with the reason.
    """
    org = db.get(Organization, org_id)
    if org is None:  # pragma: no cover - the caller just wrote it
        return "unknown-organization"
    with tenant(db, org):
        invoice = db.scalar(select(Invoice).where(Invoice.id == invoice_id, Invoice.org_id == org_id))
        if invoice is None:
            logger.warning("invoice %s no longer exists", invoice_id)
            return "unknown-invoice"
        store = get_store(db)
        fx = FxService(make_fetcher(get_settings().fx_api_url))
        try:
            invoices_service.extract(db, store, fx, org, invoice, get_extractors())
        except Exception as exc:
            db.rollback()
            logger.exception("extraction of invoice %s failed", invoice_id)
            failed = db.scalar(select(Invoice).where(Invoice.id == invoice_id))
            if failed is not None:
                failed.status = InvoiceStatus.FAILED
                failed.error = str(exc)[:500]
            db.commit()
            return InvoiceStatus.FAILED.value
        db.commit()
        return invoice.status.value


# ---------------------------------------------------------------------------- sending the digest


def dispatch_alerts(db: Session, *, notifier: Notifier | None = None) -> int:
    """Send one digest per organization for everything not yet notified. Returns digests sent.

    Grouping is the point: an alert raised just after a round waits for the next one, five minutes
    later at worst, and nobody receives four e-mails in a minute. A send that raises leaves its
    alerts unnotified, so the next round picks them up again.
    """
    sender = notifier or make_notifier()
    sent = 0
    for org in organizations(db):
        with tenant(db, org):
            alerts = unnotified_alerts(db, org)
            if not alerts:
                continue
            recipients = _recipients(db, org)
            try:
                sender.send(
                    Notification(org_id=org.id, org_name=org.name, recipients=recipients, alerts=list(alerts))
                )
            except Exception:
                logger.exception("could not send the alert digest for org %s", org.id)
                db.rollback()
                continue
            now = datetime.now(UTC)
            for alert in alerts:
                alert.notified_at = now
            db.commit()
            sent += 1
    return sent


def _recipients(db: Session, org: Organization) -> list[str]:
    """Everyone in the organization. There is no per-user notification preference yet, and inventing
    one from nothing would be worse than sending to all of a two-person team."""
    rows = db.execute(
        select(User.email)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.org_id == org.id)
        .order_by(User.email)
    ).scalars()
    return [email for email in rows if email]


# ---------------------------------------------------------------------------- helpers for the tasks


def is_daily_risk_hour(moment: datetime) -> bool:
    """Procrastinate's crons are UTC only; the users are in Paris and read this over coffee. Running
    hourly and checking the local hour is the version that does not break twice a year."""
    from zoneinfo import ZoneInfo

    return moment.astimezone(ZoneInfo(PARIS)).hour == DAILY_RISK_HOUR


def unnotified_alerts(db: Session, org: Organization) -> list[Alert]:
    return list(
        db.scalars(
            select(Alert)
            .where(Alert.org_id == org.id, Alert.notified_at.is_(None))
            .order_by(Alert.created_at)
        )
    )
