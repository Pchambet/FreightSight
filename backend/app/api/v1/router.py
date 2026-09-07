from fastapi import APIRouter

from app.api.v1 import (
    containers,
    costs,
    fx,
    imports,
    landed_costs,
    organization,
    purchase_orders,
    shipments,
    suppliers,
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
    fx.router,
):
    router.include_router(r)
