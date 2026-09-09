"""Reading purchase orders out of someone else's ERP.

Read-only, on purpose and for now: this connector is the commercial door — "it already knows your
orders" — and writing back into a customer's accounting system is a promise with a much higher price
of failure. The landed-cost write-back (Odoo's stock.landed.cost) is its own brick, later.

Amounts and quantities cross this boundary as strings, like everywhere else money travels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol, runtime_checkable

from app.core.errors import DomainError


class ErpAuthError(DomainError):
    """The credentials were refused. The message carries what the ERP said, not our guess."""

    status = 422
    code = "ERP_AUTH_FAILED"


class ErpUnavailable(DomainError):
    status = 502
    code = "ERP_UNAVAILABLE"


class ErpProtocolError(DomainError):
    """The ERP answered something we cannot use — a missing model, a renamed field."""

    status = 502
    code = "ERP_PROTOCOL_ERROR"


@dataclass(frozen=True)
class ErpIdentity:
    """What a successful connection test learned, shown back to the user as proof."""

    server_version: str
    database: str
    login: str
    user_id: int
    company: str | None = None


@dataclass(frozen=True)
class ErpLine:
    description: str
    quantity: str
    unit_price: str
    sku: str | None = None
    uom: str | None = None
    unit_weight_kg: str | None = None
    unit_volume_cbm: str | None = None
    hs_code: str | None = None


@dataclass(frozen=True)
class ErpPurchaseOrder:
    external_id: str
    number: str
    currency: str
    supplier: str | None = None
    order_date: date | None = None
    lines: list[ErpLine] = field(default_factory=list)


@runtime_checkable
class ErpConnector(Protocol):
    name: str

    def test_connection(self) -> ErpIdentity:
        """Authenticate, or raise `ErpAuthError` with the reason the ERP gave."""
        ...

    def fetch_purchase_orders(
        self, since: datetime | None = None, limit: int | None = None
    ) -> list[ErpPurchaseOrder]:
        """Confirmed orders, newest changes first. `since` filters on the ERP's own write date."""
        ...
