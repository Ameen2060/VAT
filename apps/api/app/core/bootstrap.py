"""One-time database initialization, shared by the long-running server and the
serverless (Vercel) entrypoint.

`init_db()` is idempotent and guarded by a process-level flag so it runs once per
worker/cold-start: create tables, apply the small additive column migrations, seed
the first admin, and seed the official FTA sources/rules.
"""

from __future__ import annotations

from .config import get_settings
from .database import Base, SessionLocal, engine, ensure_columns

_initialized = False


def init_db() -> None:
    global _initialized
    if _initialized:
        return

    from .. import models  # noqa: F401 — register ORM tables on the metadata

    Base.metadata.create_all(bind=engine)

    # Additive migrations (preserve existing data) until Alembic lands. On a fresh
    # database create_all already made every column, so these are no-ops; they only
    # act when upgrading an older database in place. Boolean defaults use FALSE so the
    # DDL is valid on both SQLite and PostgreSQL.
    ensure_columns(
        "reviews",
        {
            "report_key": "VARCHAR(1024)",
            "report_generated_at": "TIMESTAMP",
            "is_read": "BOOLEAN DEFAULT FALSE",
            "regime": "VARCHAR(8) DEFAULT 'vat'",
        },
    )
    ensure_columns("documents", {"regime": "VARCHAR(8) DEFAULT 'vat'"})
    ensure_columns("vat201_returns", {"refund311_json": "TEXT"})
    ensure_columns("archive_files", {"deleted_at": "TIMESTAMP", "deleted_by": "VARCHAR(255)"})
    ensure_columns("vat_rule_versions", {"requires_validation": "BOOLEAN DEFAULT FALSE"})

    from ..auth.service import bootstrap_admin
    from ..fta.seed import seed_fta
    from ..vat.tax_codes import seed_tax_codes

    settings = get_settings()
    with SessionLocal() as db:
        bootstrap_admin(db, settings.admin_email, settings.admin_password)
        # Seeding is best-effort — it must never block startup.
        try:
            seed_fta(db)
        except Exception:  # noqa: BLE001
            pass
        try:
            seed_tax_codes(db)  # populate the configurable VAT tax-code master
        except Exception:  # noqa: BLE001
            pass

    _initialized = True
