"""Frankfurter adapter: ECB reference rates, no API key. GET /{date}?from=QUOTE&to=BASE."""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

import httpx

logger = logging.getLogger(__name__)


def make_fetcher(api_url: str, timeout: float = 5.0):  # type: ignore[no-untyped-def]
    def fetch(base: str, quote: str, on_date: date) -> tuple[Decimal, date] | None:
        try:
            res = httpx.get(
                f"{api_url.rstrip('/')}/{on_date.isoformat()}",
                params={"from": quote, "to": base},
                timeout=timeout,
            )
            res.raise_for_status()
            payload = res.json()
            rate = payload["rates"][base]
            return Decimal(str(rate)), date.fromisoformat(payload["date"])
        except (httpx.HTTPError, KeyError, ValueError) as e:
            logger.warning("fx fetch failed for %s->%s on %s: %s", quote, base, on_date, e)
            return None

    return fetch
