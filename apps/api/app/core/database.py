"""Database engine/session setup.

Uses the configured DATABASE_URL. In dev this is SQLite (no external services); in
production it is PostgreSQL with pgvector. ORM models are added in Phase 1+.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

settings = get_settings()


def _normalise_db_url(url: str) -> str:
    """Accept the URL forms managed hosts hand out (Render/Heroku give
    'postgres://…' or 'postgresql://…') and route them to the psycopg 3 driver."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def _resolve_db_url() -> str:
    """Pick the database URL from the vars managed hosts inject (Neon/Vercel Postgres
    provide several). On serverless the non-pooling/direct URL is preferred: each
    short-lived invocation opens its own connection instead of borrowing a paused one
    from a pgbouncer pool, which avoids stale-connection and prepared-statement errors."""
    if os.getenv("VERCEL"):
        order = ("POSTGRES_URL_NON_POOLING", "DATABASE_URL_UNPOOLED", "DATABASE_URL", "POSTGRES_URL")
    else:
        order = ("DATABASE_URL", "POSTGRES_URL_NON_POOLING", "POSTGRES_URL", "POSTGRES_PRISMA_URL")
    for env in order:
        val = os.getenv(env)
        if val:
            return val
    return settings.database_url


DATABASE_URL = _normalise_db_url(_resolve_db_url())

# SQLite needs a flag for multi-threaded FastAPI; ensure the data dir exists.
connect_args: dict = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    db_path = DATABASE_URL.replace("sqlite:///", "")
    if db_path and db_path != ":memory:":
        # Serverless filesystems are read-only outside /tmp; never let dir creation
        # crash import. Production uses Postgres, so this only matters in dev.
        try:
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        except OSError:
            pass

engine_kwargs: dict = {"connect_args": connect_args, "future": True, "pool_pre_ping": True}
# On a serverless host (Vercel) containers are frozen/thawed between requests, which
# leaves pooled Postgres connections dead. NullPool opens a fresh connection per use
# and closes it, avoiding "server closed the connection unexpectedly" errors. We also
# disable psycopg's server-side prepared statements: if the injected URL happens to be
# a pgbouncer (transaction-pooling) endpoint, cached prepared statements collide across
# connections ("prepared statement already exists").
if DATABASE_URL.startswith("postgresql"):
    # Wait (up to 10s) for the server to accept a connection rather than failing
    # instantly — serverless Postgres (Neon) auto-suspends when idle and needs a
    # moment to wake on the first request after a quiet period.
    connect_args["connect_timeout"] = 10
if DATABASE_URL.startswith("postgresql") and os.getenv("VERCEL"):
    from sqlalchemy.pool import NullPool

    engine_kwargs["poolclass"] = NullPool
    connect_args["prepare_threshold"] = None

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def _wake_and_verify(db: Session) -> None:
    """Confirm the connection is live before the endpoint uses it, retrying briefly.

    Serverless Postgres (Neon free tier) suspends when idle; the first query after a
    quiet period can fail once while the compute wakes. Retrying here — with a short
    backoff — means a waking database is transparent to the user instead of surfacing
    as a 500/503. Runs in FastAPI's threadpool, so the sleeps don't block the loop.
    """
    from time import sleep

    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError, OperationalError

    last: Exception | None = None
    for attempt in range(4):
        try:
            db.execute(text("SELECT 1"))
            return
        except (OperationalError, DBAPIError) as exc:  # connection-class errors only
            last = exc
            db.rollback()
            sleep(0.5 * (attempt + 1))  # 0.5s, 1s, 1.5s
    if last is not None:
        raise last


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        _wake_and_verify(db)
        yield db
    finally:
        db.close()


def ensure_columns(table: str, columns: dict[str, str]) -> None:
    """Lightweight additive migration: ADD COLUMN for any missing columns, preserving
    data. Bridges `create_all` until Alembic is introduced (Phase 4). No-op if the
    table doesn't exist yet or the column is already present.
    """
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if table not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns(table)}
    with engine.begin() as conn:
        for name, ddl_type in columns.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}"))
