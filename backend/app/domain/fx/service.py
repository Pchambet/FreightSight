"""Fixed FX rates. A rate is looked up in `fx_rates`, fetched once from the ECB (via Frankfurter) if missing,
and never converted on read: the caller stores (rate, date, source) on the row that used it."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.errors import Unprocessable
from app.domain.models import FxRate

# 1 unit of `quote` = `rate` units of `base`. Injectable so tests never touch the network.
Fetcher = Callable[[str, str, date], tuple[Decimal, date] | None]


@dataclass(frozen=True)
class ResolvedRate:
    rate: Decimal
    rate_date: date
    source: str


class FxService:
    def __init__(self, fetcher: Fetcher):
        self._fetch = fetcher

    def resolve(
        self,
        db: Session,
        base: str,
        quote: str,
        on_date: date,
        manual_rate: Decimal | None = None,
    ) -> ResolvedRate:
        if manual_rate is not None:
            if manual_rate <= 0:
                raise Unprocessable("fx_rate must be > 0", code="FX_RATE_INVALID")
            return ResolvedRate(manual_rate, on_date, "manual")
        if base == quote:
            return ResolvedRate(Decimal("1"), on_date, "same")
        row = db.get(FxRate, (base, quote, on_date))
        if row is not None:
            return ResolvedRate(row.rate, row.rate_date, row.source)
        fetched = self._fetch(base, quote, on_date)
        if fetched is None:
            raise Unprocessable(
                f"No {quote}→{base} rate available for {on_date.isoformat()}. Provide fx_rate manually.",
                code="FX_RATE_UNAVAILABLE",
                base=base,
                quote=quote,
                date=on_date.isoformat(),
            )
        rate, actual_date = fetched
        db.merge(FxRate(base=base, quote=quote, rate_date=on_date, rate=rate, source="ecb"))
        db.flush()
        return ResolvedRate(rate, actual_date, "ecb")
