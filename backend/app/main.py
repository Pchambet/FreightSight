from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, event, text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1 import schemas
from app.api.v1.router import router as v1_router
from app.core.db import assert_migrated, get_engine
from app.core.errors import DomainError
from app.core.settings import get_settings
from app.core.tenancy import ORG_GUC

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("freightsight")


def install_guc_reset(engine: Engine) -> None:
    """Clear the tenant variable when a pooled connection is returned, so it never leaks across requests."""

    @event.listens_for(engine, "checkin")
    def _reset(dbapi_connection, _record):  # type: ignore[no-untyped-def]
        try:
            cur = dbapi_connection.cursor()
            cur.execute(f"RESET {ORG_GUC}")
            cur.close()
            # RESET opens a transaction on a non-autocommit DBAPI connection; close it, or the
            # next checkout fails with "can't change autocommit now: connection in transaction".
            dbapi_connection.rollback()
        except Exception:  # pragma: no cover - connection already broken
            pass


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    engine = get_engine()
    install_guc_reset(engine)
    if settings.app_env != "test":
        assert_migrated(engine)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="FreightSight API",
        version="0.2.0",
        description="Landed cost allocation and container tracking for SMB importers. Pre-alpha.",
        lifespan=lifespan,
        docs_url=None if settings.is_prod else "/docs",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
    )

    @app.exception_handler(DomainError)
    async def domain_problem(_: Request, exc: DomainError) -> JSONResponse:
        body = schemas.Problem(
            title=_title(exc.status), status=exc.status, code=exc.code, detail=exc.message, errors=exc.errors
        ).model_dump()
        body.update(exc.extra)
        return JSONResponse(body, status_code=exc.status)

    @app.exception_handler(StarletteHTTPException)
    async def http_problem(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else None
        body = schemas.Problem(
            title=_title(exc.status_code), status=exc.status_code, detail=detail
        ).model_dump()
        if isinstance(exc.detail, dict):
            body.update(exc.detail)
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
            title="Validation error",
            status=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="VALIDATION",
            errors=errors,
        ).model_dump()
        return JSONResponse(body, status_code=status.HTTP_422_UNPROCESSABLE_CONTENT)

    @app.get("/", tags=["system"])
    def root() -> dict[str, str]:
        return {"service": "FreightSight API", "status": "pre-alpha", "api": "/api/v1"}

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

    app.include_router(v1_router)
    return app


def _title(code: int) -> str:
    return {
        400: "Bad request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not found",
        409: "Conflict",
        413: "Content too large",
        422: "Unprocessable content",
        501: "Not implemented",
    }.get(code, "Error")


app = create_app()
