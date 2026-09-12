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
from app.core.tenancy import TenantSession, set_current_org
from app.domain.alerts.notifier import Notification, Notifier, make_notifier
from app.domain.alerts.service import raise_alert, raise_dnd_risk_alert
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
    ErpSyncStatus,
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
#: How many containers in a row a provider may fail to answer for before we stop asking it in this
#: sweep. Three, because one is a bad container and two is a coincidence.
CIRCUIT_TRIPS_AFTER = 3
#: How many times a failed delivery is retried before it is left alone.
MAX_DELIVERY_ATTEMPTS = 5
#: The hour, in Europe/Paris, at which the demurrage pass runs.
DAILY_RISK_HOUR = 6
PARIS = "Europe/Paris"

RISK_ORDER = [DndRisk.NONE, DndRisk.LOW, DndRisk.MEDIUM, DndRisk.HIGH, DndRisk.INCURRING]


class ProviderCircuit:
    """Stops asking a provider that has stopped answering, for the rest of a sweep.

    Without this, an outage at a provider costs one timeout per tracked container: bounded per call
    since the timeout audit, but multiplied by every container, on a job that holds a queueing lock.
    A hundred boxes and a silent provider is an hour of a worker spent learning the same thing a
    hundred times.

    Per sweep rather than persisted: the next run starts by trying again, which is what you want
    from an outage that is usually minutes long.
    """

    def __init__(self, trips_after: int = CIRCUIT_TRIPS_AFTER) -> None:
        self.trips_after = trips_after
        self.failures: dict[str, int] = {}
        self.tripped: set[str] = set()

    def is_open(self, provider: str) -> bool:
        """True when we have stopped asking this provider."""
        return provider in self.tripped

    def failed(self, provider: str) -> bool:
        """Record a provider that could not be reached. True when this is the one that trips it."""
        self.failures[provider] = self.failures.get(provider, 0) + 1
        if self.failures[provider] >= self.trips_after and provider not in self.tripped:
            self.tripped.add(provider)
            return True
        return False

    def answered(self, provider: str) -> None:
        """A provider that answers is not down, whatever the answer was."""
        self.failures.pop(provider, None)


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
        try:
            provider = provider_factory(delivery.provider)
        except Exception:
            # A provider whose key has been removed, or a name no longer in the registry. The body
            # stays in the table and this returns to it; what it must not do is stop the *other*
            # providers' deliveries being replayed behind it.
            logger.exception("no provider for stored delivery %s", delivery.id)
            continue
        # process_stored_delivery never raises: a delivery that cannot be understood is marked,
        # not thrown. Anything that escapes anyway is a bug, and one bad body is not a reason to
        # abandon the rest of the queue.
        try:
            process_stored_delivery(db, provider, delivery, attempt=attempts + 1, now=moment)
        except Exception:  # pragma: no cover - the callee is written not to raise
            logger.exception("replaying delivery %s failed", delivery.id)
            db.rollback()
            continue
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
    quiet. Returns the number of subscriptions polled.

    Two things a provider outage must not be allowed to do, and both used to happen: mark every
    customer's containers as failed while telling them to go and check the carrier's site, and spend
    one timeout per container finding that out.

    A third, subtler one: telling only the organization the circuit happened to trip on. Whose turn
    it was is an accident of iteration order — every organization whose polling stopped this round
    is told, once, and only once the provider is really down rather than on a single timeout.
    """
    moment = now or datetime.now(UTC)
    circuit = ProviderCircuit()
    polled = 0
    stopped: dict[str, dict[UUID, Organization]] = {}
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
                if circuit.is_open(subscription.provider):
                    # Asking again costs a timeout. This organization's tracking has stopped all
                    # the same, so it is on the list of people to tell.
                    stopped.setdefault(subscription.provider, {})[org.id] = org
                    continue
                container = db.get(Container, subscription.container_id)
                if container is None:  # pragma: no cover - foreign key says otherwise
                    continue
                polled += 1
                try:
                    outcome = _poll_one(db, org, subscription, container, moment, provider_factory)
                except Exception:
                    # One container's surprise — a payload shape nobody expected, a bug in a parser
                    # — must not cost every other organization its round.
                    logger.exception("polling failed for container %s", subscription.container_id)
                    db.rollback()
                    continue
                if outcome != "unreachable":
                    circuit.answered(subscription.provider)
                else:
                    stopped.setdefault(subscription.provider, {})[org.id] = org
                    circuit.failed(subscription.provider)
            db.commit()
    _announce_outages(db, stopped, circuit, moment)
    return polled


def _announce_outages(
    db: Session,
    stopped: dict[str, dict[UUID, Organization]],
    circuit: ProviderCircuit,
    moment: datetime,
) -> None:
    """Tell every organization whose tracking stopped, once the provider is confirmed down.

    At the end rather than as it happens: an organization polled before the third failure would
    otherwise hear nothing, and an organization polled after it would hear about a provider that
    answered again two containers later.
    """
    for provider, affected in stopped.items():
        if not circuit.is_open(provider):
            continue  # a timeout or two, and then it answered: not an outage anybody needs told
        for org in affected.values():
            with tenant(db, org):
                _provider_is_down(db, org, provider, moment)
                db.commit()


def _provider_is_down(db: Session, org: Organization, provider: str, moment: datetime) -> None:
    """One alert about the provider, instead of one alert per container about the containers."""
    logger.warning(
        "tracking provider not answering: polling stopped for this round",
        extra={"provider": provider, "org_id": str(org.id)},
    )
    raise_alert(
        db,
        org.id,
        kind=AlertKind.TRACKING_PROVIDER_DOWN,
        severity=AlertSeverity.WARNING,
        title=f"{provider} is not answering",
        body=(
            f"We could not reach {provider} for several containers in a row, so tracking updates "
            "are paused until it answers again. Nothing is wrong with the containers themselves, "
            "and nothing needs doing here: the next round picks up where this one stopped."
        ),
        dedup_key=f"tracking-provider-down:{provider}:{moment.date().isoformat()}",
        payload={"provider": provider},
    )


def _poll_one(
    db: Session,
    org: Organization,
    subscription: TrackingSubscription,
    container: Container,
    moment: datetime,
    provider_factory: ProviderFactory,
) -> str:
    """Ask about one container. Returns `ingested`, `quiet`, or `unreachable`.

    The three are not the same and used to be treated as two. "The provider answered and had
    nothing" is about this container and is worth telling its owner about. "We could not reach the
    provider" is about us and our supplier: saying "check the container on the carrier's own site"
    then accuses the customer's carrier of something our own outage caused, and marking the
    container FAILED makes their screen red for a reason that has nothing to do with their freight.
    """
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
            subscription.last_error = exc.message
            db.flush()
            return "unreachable"
    else:
        reason = "no provider reference: this container is tracked webhook-only"
    if ingested:
        return "ingested"
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
        payload={
            "provider": subscription.provider,
            "days_since_subscribed": days,
            "hours": int(STALE_AFTER.total_seconds() // 3600),
            "reason": reason,
        },
    )
    subscription.last_error = reason or "no data"
    if subscription.status == "active" and container.tracking_state is TrackingState.ACTIVE:
        container.tracking_state = TrackingState.FAILED
    db.flush()
    return "quiet"


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
    circuit = ProviderCircuit()
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
                    if circuit.is_open(subscription.provider):
                        continue  # not answering; the next run will unsubscribe these
                    try:
                        provider_factory(subscription.provider).unsubscribe(subscription.provider_ref)
                    except (ProviderNotConfigured, ProviderUnavailable) as exc:
                        # The provider will keep charging until someone sorts it out; that is worth
                        # saying, and worth retrying, so the subscription stays open.
                        logger.warning(
                            "could not unsubscribe container %s: %s", container.container_number, exc
                        )
                        subscription.last_error = exc.message
                        circuit.failed(subscription.provider)
                        continue
                    circuit.answered(subscription.provider)
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
    raise_dnd_risk_alert(db, org, container, moment)


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
                    payload={
                        "delta_hours": str(hours),
                        "eta": row.eta.isoformat(),
                        "previous_eta": row.previous_eta.isoformat() if row.previous_eta else None,
                    },
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


# ---------------------------------------------------------------------------- ERP


def sync_erp(db: Session, org_id: UUID | None = None, *, now: datetime | None = None) -> int:
    """Read every active ERP connection that is due, or one organization's. Returns syncs that worked.

    One failing customer's Odoo must not stop the others: each connection is its own transaction and
    its own run row, and a failure is recorded rather than raised. A connection that keeps failing is
    left alone for a while — see `erp_service.backoff_for` — so a customer whose server has been down
    for a week is not dialled every morning to write the same row again. Asking for one organization
    by name (`org_id`) ignores the backoff: that is a person asking, not the schedule.
    """
    from app.core.auth import Principal
    from app.domain.erp import service as erp_service
    from app.domain.models import ErpConnection, MemberRole

    moment = now or datetime.now(UTC)
    succeeded = 0
    for org in organizations(db):
        if org_id is not None and org.id != org_id:
            continue
        with tenant(db, org):
            connection = db.scalar(
                select(ErpConnection).where(ErpConnection.org_id == org.id, ErpConnection.active.is_(True))
            )
            if connection is None:
                continue
            if org_id is None and not erp_service.due_for_sync(connection, moment):
                logger.info(
                    "erp sync skipped: still backing off",
                    extra={
                        "org_id": str(org.id),
                        "retry_after": connection.retry_after.isoformat() if connection.retry_after else None,
                        "consecutive_failures": connection.consecutive_failures,
                    },
                )
                continue
            # The import pipeline works for a person; here the person is the schedule. The principal
            # is synthetic and carries no user, which is exactly what the audit trail should show.
            principal = Principal(org_id=org.id, user_id=None, role=MemberRole.OWNER, via="dev")
            t = TenantSession(db, principal, org)
            try:
                erp_service.sync(t, connection)
                db.commit()
                succeeded += 1
            except Exception as exc:
                # The reason has to be read off the exception now: the rollback below throws away
                # the run row and the connection fields the service had already filled in.
                reason = f"{type(exc).__name__}: {exc}" if not str(exc) else str(exc)
                db.rollback()
                logger.exception("ERP sync failed for org %s", org.id)
                _record_failure(db, org, connection.id, reason, moment)
    return succeeded


def _record_failure(db: Session, org: Organization, connection_id: UUID, reason: str, at: datetime) -> None:
    """Write the failure again after the rollback that discarded it, with what actually went wrong.

    "See the application logs" is not something a customer can act on, and they cannot read our logs
    anyway. What goes on the screen is the ERP's own words — "Odoo is unreachable at …: timed out".
    """
    from app.domain.erp import service as erp_service
    from app.domain.models import ErpConnection, ErpSyncRun

    db.add(
        ErpSyncRun(
            org_id=org.id,
            connection_id=connection_id,
            status=ErpSyncStatus.FAILED,
            finished_at=at,
            error=reason[:1000],
        )
    )
    fresh = db.get(ErpConnection, connection_id)
    if fresh is not None:
        erp_service.note_failure(fresh, reason, at=at)
    db.commit()


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
                    Notification(
                        org_id=org.id,
                        org_name=org.name,
                        recipients=recipients,
                        alerts=list(alerts),
                        locale=org.locale,
                        container_numbers=_container_numbers(db, alerts),
                    )
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


def _container_numbers(db: Session, alerts: list[Alert]) -> dict[UUID, str]:
    """The box numbers the digest's sentences name, in one query rather than one per alert."""
    ids = {alert.container_id for alert in alerts if alert.container_id is not None}
    if not ids:
        return {}
    rows = db.execute(select(Container.id, Container.container_number).where(Container.id.in_(ids))).all()
    return {row.id: row.container_number for row in rows}


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
