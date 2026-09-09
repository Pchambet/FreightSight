from fastapi import APIRouter

from app.api.v1 import (
    alerts,
    audit,
    containers,
    costs,
    erp,
    exports,
    fx,
    imports,
    invoices,
    landed_costs,
    organization,
    purchase_orders,
    rate_cards,
    reports,
    shipments,
    suppliers,
    tracking,
    webhooks,
)

router = APIRouter(prefix="/api/v1")
for r in (
    organization.router,
    suppliers.router,
    purchase_orders.router,
    rate_cards.router,
    reports.router,
    shipments.router,
    containers.router,
    erp.router,
    exports.router,
    costs.router,
    landed_costs.router,
    imports.router,
    invoices.router,
    fx.router,
    alerts.router,
    audit.router,
    tracking.router,
    webhooks.router,
):
    router.include_router(r)
