from fastapi import APIRouter

from app.api.v1 import (
    alerts,
    audit,
    containers,
    costs,
    fx,
    imports,
    invoices,
    landed_costs,
    organization,
    purchase_orders,
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
    shipments.router,
    containers.router,
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
