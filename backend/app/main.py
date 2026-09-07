from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import schemas
from app.api import containers, purchase_orders
from app.config import get_settings
from app.db import assert_migrated, get_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("freightsight")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if settings.app_env != "test":
        assert_migrated(get_engine())
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="FreightSight API",
        version="0.1.0",
        description="Landed cost allocation and container tracking for SMB importers. Pre-alpha.",
        lifespan=lifespan,
        docs_url=None if settings.is_prod else "/docs",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["*"],
    )

    @app.exception_handler(StarletteHTTPException)
    async def http_problem(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else None
        extra: dict[str, object] = exc.detail if isinstance(exc.detail, dict) else {}
        body = schemas.Problem(
            title=_title(exc.status_code), status=exc.status_code, detail=detail
        ).model_dump()
        body.update(extra)
        return JSONResponse(body, status_code=exc.status_code, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def validation_problem(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {
                "field": ".".join(str(p) for p in e["loc"] if p != "body"),
                "code": e["type"],
                "message": e["msg"],
            }
            for e in exc.errors()
        ]
        body = schemas.Problem(
            title="Validation error", status=status.HTTP_422_UNPROCESSABLE_CONTENT, errors=errors
        ).model_dump()
        return JSONResponse(body, status_code=status.HTTP_422_UNPROCESSABLE_CONTENT)

    @app.get("/", tags=["system"])
    def root() -> dict[str, str]:
        return {"service": "FreightSight API", "status": "pre-alpha"}

    @app.get("/healthz", tags=["system"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["system"])
    def readyz() -> JSONResponse:
        try:
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as e:
            logger.error("readiness failed: %s", e)
            return JSONResponse({"status": "unavailable"}, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
        return JSONResponse({"status": "ready"})

    app.include_router(containers.router)
    app.include_router(purchase_orders.router)
    return app


def _title(code: int) -> str:
    return {
        400: "Bad request",
        404: "Not found",
        409: "Conflict",
        413: "Content too large",
        422: "Unprocessable content",
        501: "Not implemented",
    }.get(code, "Error")


app = create_app()
