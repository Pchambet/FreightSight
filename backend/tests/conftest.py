"""Test harness: a real Postgres (TEST_DATABASE_URL, else a throwaway container), migrations applied once,
each test wrapped in a transaction that is rolled back."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("CORS_ORIGINS", '["http://localhost:3000"]')


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        yield url
        return
    try:
        from testcontainers.community.postgres import PostgresContainer
    except ImportError:  # older testcontainers
        from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:17", driver="psycopg") as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    os.environ["DATABASE_URL"] = database_url
    cfg = AlembicConfig(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "migrations"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    eng = create_engine(database_url)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    """Transaction-per-test with SAVEPOINT support (SQLAlchemy 'join external transaction' recipe)."""
    connection = engine.connect()
    outer = connection.begin()
    session = sessionmaker(
        bind=connection, autoflush=False, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess: Session, trans):  # type: ignore[no-untyped-def]
        if trans.nested and not trans._parent.nested and not sess.in_transaction():
            sess.begin_nested()

    session.begin_nested()
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


@pytest.fixture
def org_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def client(db: Session, engine: Engine, org_id: uuid.UUID) -> Iterator[TestClient]:
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, headers={"X-Org-Id": str(org_id)}) as c:
        yield c
    app.dependency_overrides.clear()
