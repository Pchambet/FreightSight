"""Task declarations: what runs in the background, and when.

The bodies are in `handlers.py` as plain functions taking a session, so they can be tested without a
worker or a queue. Here they only get a name, a schedule and a retry policy.

Procrastinate's periodic scheduling is UTC-only and it passes the tick timestamp as the first
argument. Anything that has to happen at a local hour therefore runs hourly and checks the local
clock itself — see `handlers.is_daily_risk_hour`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from procrastinate import RetryStrategy

from app.jobs import handlers
from app.jobs.app import get_app

logger = logging.getLogger(__name__)

app = get_app()


def _moment(timestamp: int) -> datetime:
    return datetime.fromtimestamp(timestamp, tz=UTC)


@app.periodic(cron="*/15 * * * *")
@app.task(
    name="tracking.retry_failed_deliveries",
    queueing_lock="tracking:retry_failed_deliveries",
    retry=RetryStrategy(max_attempts=3, exponential_wait=30),
)
def retry_failed_deliveries(timestamp: int) -> None:
    """Replay webhook deliveries that failed on our side, with a bounded number of attempts."""
    with handlers.session() as db:
        count = handlers.retry_failed_deliveries(db, now=_moment(timestamp))
    logger.info("retried %s failed tracking deliveries", count)


@app.periodic(cron="0 */4 * * *")
@app.task(
    name="tracking.poll_stale_subscriptions",
    queueing_lock="tracking:poll_stale_subscriptions",
    retry=RetryStrategy(max_attempts=3, exponential_wait=60),
)
def poll_stale_subscriptions(timestamp: int) -> None:
    """Ask the provider about containers whose feed has gone quiet, and alert if it stays quiet."""
    with handlers.session() as db:
        count = handlers.poll_stale_subscriptions(db, now=_moment(timestamp))
    logger.info("polled %s stale subscriptions", count)


@app.periodic(cron="30 4 * * *")
@app.task(
    name="tracking.end_delivered",
    queueing_lock="tracking:end_delivered",
    retry=RetryStrategy(max_attempts=3, exponential_wait=60),
)
def end_delivered_subscriptions(timestamp: int) -> None:
    """Stop paying to watch containers that were delivered a week ago."""
    with handlers.session() as db:
        ended = handlers.end_delivered_subscriptions(db, now=_moment(timestamp))
    logger.info("ended %s tracking subscriptions on delivered containers", ended)


@app.periodic(cron="0 * * * *")
@app.task(
    name="dnd.recompute_risk",
    queueing_lock="dnd:recompute_risk",
    retry=RetryStrategy(max_attempts=3, exponential_wait=60),
)
def recompute_dnd_risk(timestamp: int) -> None:
    """The morning demurrage pass, at 06:00 Europe/Paris. Hourly ticks, one working hour."""
    moment = _moment(timestamp)
    if not handlers.is_daily_risk_hour(moment):
        return
    with handlers.session() as db:
        changed = handlers.recompute_dnd_risk(db, now=moment)
    logger.info("demurrage risk changed on %s containers", changed)


@app.periodic(cron="*/15 * * * *")
@app.task(
    name="tracking.alert_on_eta_changes",
    queueing_lock="tracking:alert_on_eta_changes",
    retry=RetryStrategy(max_attempts=3, exponential_wait=30),
)
def alert_on_eta_changes(timestamp: int) -> None:
    """Turn recent ETA history into alerts."""
    with handlers.session() as db:
        raised = handlers.alert_on_eta_changes(db, now=_moment(timestamp))
    logger.info("raised %s ETA alerts", raised)


@app.periodic(cron="*/5 * * * *")
@app.task(
    name="alerts.dispatch",
    queueing_lock="alerts:dispatch",
    retry=RetryStrategy(max_attempts=3, exponential_wait=60),
)
def dispatch_alerts(timestamp: int) -> None:
    """One digest per organization, every five minutes, for whatever is not yet notified."""
    with handlers.session() as db:
        sent = handlers.dispatch_alerts(db)
    logger.info("sent %s alert digests", sent)


@app.task(
    name="invoices.extract",
    retry=RetryStrategy(max_attempts=3, exponential_wait=30),
)
def extract_invoice(org_id: str, invoice_id: str) -> None:
    """Read an uploaded invoice. Deferred inside the upload's own transaction, so a job never exists
    for an invoice that was never stored."""
    from uuid import UUID

    with handlers.session() as db:
        status = handlers.extract_invoice(db, UUID(org_id), UUID(invoice_id))
    logger.info("invoice %s extraction ended in %s", invoice_id, status)


@app.periodic(cron="15 5 * * *")
@app.task(
    name="erp.sync",
    queueing_lock="erp:sync",
    retry=RetryStrategy(max_attempts=2, exponential_wait=120),
)
def sync_erp(timestamp: int) -> None:
    """The daily read of every connected ERP. On-demand syncs go through the API, not through here."""
    with handlers.session() as db:
        synced = handlers.sync_erp(db)
    logger.info("synchronised %s ERP connection(s)", synced)
