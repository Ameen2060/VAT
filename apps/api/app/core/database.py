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


DATABASE_URL = _normalise_db_url(settings.database_url)

# SQLite needs a flag for multi-threaded FastAPI; ensure the data dir exists.
connect_args: dict = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    db_path = DATABASE_URL.replace("sqlite:///", "")
    if db_path and db_path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

engine = create_engine(
    DATABASE_URL, connect_args=connect_args, future=True, pool_pre_ping=True
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
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
