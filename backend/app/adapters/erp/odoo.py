"""Odoo over XML-RPC, verified against a real Odoo 17.

Two endpoints and nothing else: `/xmlrpc/2/common` to authenticate, `/xmlrpc/2/object` to read. No
`odoorpc` dependency for what is two proxies and a method call, and no HTTP session to keep alive.

Three things a real Odoo taught me, which the fixtures now encode:

  * **A line's quantity is in the line's unit of measure, not the product's.** The demo data orders
    "20 Dozens" of a product whose weight is per unit. Importing 20 where the customer means 240
    would understate every weight-based allocation, so quantities are converted through the UoM
    ratio and the original unit is kept in the description.
  * **`hs_code` does not exist on `product.product` in Odoo 17 Community.** It arrives with
    localisation or Enterprise modules. The adapter asks `fields_get` what exists and reads the
    field only if it is there, rather than failing on a customer who does not have it.
  * **A wrong password is not an exception**: `authenticate` returns `False`. A wrong *field* is a
    `Fault` carrying a full Python traceback, whose last line is the only part worth showing.
"""

from __future__ import annotations

import logging
import xmlrpc.client
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.domain.erp.ports import (
    ErpAuthError,
    ErpIdentity,
    ErpLine,
    ErpProtocolError,
    ErpPurchaseOrder,
    ErpUnavailable,
)

logger = logging.getLogger(__name__)

NAME = "odoo"
#: Orders in these states are commitments; a draft is not something to plan a landed cost around.
CONFIRMED_STATES = ("purchase", "done")
#: Fields we ask for on the product, when the instance has them.
OPTIONAL_PRODUCT_FIELDS = ("hs_code", "l10n_in_hsn_code")

ProxyFactory = Callable[[str], Any]

#: The precision of `po_lines.unit_price`, so a converted price is stored as it will be read.
PRICE_PRECISION = Decimal("0.0001")


def _default_proxy(url: str) -> Any:
    return xmlrpc.client.ServerProxy(url, allow_none=True)


def _decimal(value: Any) -> str | None:
    """Odoo speaks float over XML-RPC; it becomes a string here and stays one."""
    if value in (None, False, ""):
        return None
    try:
        return f"{Decimal(str(value)):f}"
    except (InvalidOperation, ValueError):
        return None


def _fault_reason(exc: xmlrpc.client.Fault) -> str:
    """The last meaningful line of an Odoo traceback, which is the part a person can act on."""
    lines = [line.strip() for line in str(exc.faultString or "").splitlines() if line.strip()]
    return lines[-1] if lines else "Odoo returned an error"


class OdooConnector:
    name = NAME

    def __init__(
        self,
        url: str,
        database: str,
        login: str,
        api_key: str,
        *,
        proxy_factory: ProxyFactory | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        self.database = database
        self.login = login
        self.api_key = api_key
        # Resolved here rather than as a default argument, so the module-level factory can be
        # replaced (a test transport, one day a proxy) without rebuilding this class.
        self._proxy_factory = proxy_factory or _default_proxy
        self._uid: int | None = None

    # ------------------------------------------------------------------ plumbing

    def _common(self) -> Any:
        return self._proxy_factory(f"{self.url}/xmlrpc/2/common")

    def _models(self) -> Any:
        return self._proxy_factory(f"{self.url}/xmlrpc/2/object")

    def _authenticate(self) -> int:
        if self._uid is not None:
            return self._uid
        try:
            uid = self._common().authenticate(self.database, self.login, self.api_key, {})
        except xmlrpc.client.Fault as exc:
            # A database that does not exist comes back as a Fault, not as False.
            raise ErpAuthError(f"Odoo refused the connection: {_fault_reason(exc)}") from exc
        except OSError as exc:
            raise ErpUnavailable(f"Odoo is unreachable at {self.url}: {exc}") from exc
        if not uid:
            raise ErpAuthError(
                f"Odoo refused the credentials for {self.login!r} on database {self.database!r}. "
                "Check the login and the API key (Preferences → Account Security → API keys)."
            )
        self._uid = int(uid)
        return self._uid

    def _kw(self, model: str, method: str, *args: Any, **kwargs: Any) -> Any:
        uid = self._authenticate()
        try:
            return self._models().execute_kw(
                self.database, uid, self.api_key, model, method, list(args), kwargs
            )
        except xmlrpc.client.Fault as exc:
            raise ErpProtocolError(f"Odoo could not answer {model}.{method}: {_fault_reason(exc)}") from exc
        except OSError as exc:
            raise ErpUnavailable(f"Odoo is unreachable at {self.url}: {exc}") from exc

    # ------------------------------------------------------------------ the port

    def test_connection(self) -> ErpIdentity:
        try:
            version = self._common().version().get("server_version", "unknown")
        except OSError as exc:
            raise ErpUnavailable(f"Odoo is unreachable at {self.url}: {exc}") from exc
        uid = self._authenticate()
        user = self._kw("res.users", "read", [uid], fields=["name", "company_id"])
        company = None
        if user and user[0].get("company_id"):
            company = user[0]["company_id"][1]
        return ErpIdentity(
            server_version=str(version),
            database=self.database,
            login=self.login,
            user_id=uid,
            company=company,
        )

    def fetch_purchase_orders(
        self, since: datetime | None = None, limit: int | None = None
    ) -> list[ErpPurchaseOrder]:
        domain: list[Any] = [["state", "in", list(CONFIRMED_STATES)]]
        if since is not None:
            domain.append(["write_date", ">=", since.strftime("%Y-%m-%d %H:%M:%S")])
        orders = self._kw(
            "purchase.order",
            "search_read",
            domain,
            fields=["name", "partner_id", "currency_id", "date_order", "state", "order_line"],
            order="write_date",
            **({"limit": limit} if limit else {}),
        )
        if not orders:
            return []

        line_ids = [line_id for order in orders for line_id in order.get("order_line") or []]
        lines = (
            self._kw(
                "purchase.order.line",
                "search_read",
                [["id", "in", line_ids]],
                fields=[
                    "order_id",
                    "name",
                    "product_id",
                    "product_qty",
                    "price_unit",
                    "product_uom",
                    "display_type",
                ],
            )
            if line_ids
            else []
        )
        product_fields = [
            "default_code",
            "name",
            "weight",
            "volume",
            "uom_id",
            *self._optional_fields(),
        ]
        product_ids = sorted({ln["product_id"][0] for ln in lines if ln.get("product_id")})
        products = (
            {p["id"]: p for p in self._kw("product.product", "read", product_ids, fields=product_fields)}
            if product_ids
            else {}
        )
        uom_ids = sorted(
            {ln["product_uom"][0] for ln in lines if ln.get("product_uom")}
            | {p["uom_id"][0] for p in products.values() if p.get("uom_id")}
        )
        uoms = (
            {u["id"]: u for u in self._kw("uom.uom", "read", uom_ids, fields=["name", "factor_inv"])}
            if uom_ids
            else {}
        )

        by_order: dict[int, list[ErpLine]] = {}
        for raw in lines:
            if raw.get("display_type"):
                continue  # a section header or a note, not something bought
            by_order.setdefault(raw["order_id"][0], []).append(self._line(raw, products, uoms))

        return [
            ErpPurchaseOrder(
                external_id=str(order["id"]),
                number=str(order["name"]),
                currency=str(order["currency_id"][1]) if order.get("currency_id") else "",
                supplier=str(order["partner_id"][1]) if order.get("partner_id") else None,
                order_date=_as_date(order.get("date_order")),
                lines=by_order.get(order["id"], []),
            )
            for order in orders
        ]

    # ------------------------------------------------------------------ details

    def _optional_fields(self) -> list[str]:
        """Ask what this instance actually has: HS codes come from modules many customers lack."""
        try:
            available = self._kw("product.product", "fields_get", [], attributes=["type"])
        except ErpProtocolError:  # pragma: no cover - an Odoo that refuses fields_get is broken
            return []
        return [name for name in OPTIONAL_PRODUCT_FIELDS if name in available]

    def _line(self, raw: dict[str, Any], products: dict[int, Any], uoms: dict[int, Any]) -> ErpLine:
        product = products.get(raw["product_id"][0]) if raw.get("product_id") else None
        line_uom = uoms.get(raw["product_uom"][0]) if raw.get("product_uom") else None
        product_uom = uoms.get(product["uom_id"][0]) if product and product.get("uom_id") else None

        quantity = Decimal(str(raw.get("product_qty") or 0))
        unit_price = Decimal(str(raw.get("price_unit") or 0))
        uom_name = line_uom["name"] if line_uom else None
        if line_uom and product_uom and line_uom["id"] != product_uom["id"]:
            # "20 Dozens" is 240 of the thing the product's weight is expressed in. Convert, and
            # divide the price by the same ratio so the line total is untouched.
            ratio = Decimal(str(line_uom.get("factor_inv") or 1)) / Decimal(
                str(product_uom.get("factor_inv") or 1)
            )
            if ratio > 0:
                quantity *= ratio
                # Four decimals, the precision of the column this ends up in. On "20 Dozens at 500"
                # that is 240 at 41.6667, whose total is off by eight thousandths of a currency
                # unit — visible in a test, invisible in a landed cost, and honest about where it
                # comes from.
                unit_price = (unit_price / ratio).quantize(PRICE_PRECISION)

        hs_code = None
        if product:
            for candidate in OPTIONAL_PRODUCT_FIELDS:
                value = product.get(candidate)
                if value:
                    hs_code = str(value)
                    break

        return ErpLine(
            description=str(raw.get("name") or (product or {}).get("name") or ""),
            quantity=f"{quantity:f}",
            unit_price=f"{unit_price:f}",
            sku=(product or {}).get("default_code") or None,
            uom=uom_name,
            unit_weight_kg=_decimal((product or {}).get("weight")),
            unit_volume_cbm=_decimal((product or {}).get("volume")),
            hs_code=hs_code,
        )


def _as_date(value: Any) -> date | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()  # noqa: DTZ007 - a date, no zone
    except ValueError:
        return None
