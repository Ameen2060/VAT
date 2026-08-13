"""FastAPI application entrypoint.

Phase 0 exposes a health check and a working `/api/review` endpoint that runs the
deterministic VAT rule engine against a structured invoice. File upload, OCR and AI
extraction arrive in Phase 1 and will feed the same engine.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api.routes_ai import router as ai_router
from .api.routes_archive import router as archive_router
from .api.routes_assistant import router as assistant_router
from .api.routes_auth import router as auth_router
from .api.routes_ct import router as ct_router
from .api.routes_fta import router as fta_router
from .api.routes_knowledge import router as knowledge_router
from .api.routes_review import router as review_router
from .api.routes_vat201 import router as vat201_router
from .auth.deps import get_current_user
from .core.config import get_settings
from .core.database import Base, engine
from .vat.rules import review_invoice
from .vat.schemas import Invoice, ReviewResult

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Import models so they register on the metadata, then create tables.
    # (Phase 3 will replace create_all with Alembic migrations.)
    from . import models  # noqa: F401
    from .core.database import ensure_columns

    Base.metadata.create_all(bind=engine)
    # Additive migrations (preserve existing data) until Alembic lands in Phase 4.
    ensure_columns(
        "reviews",
        {
            "report_key": "VARCHAR(1024)",
            "report_generated_at": "TIMESTAMP",
            "is_read": "BOOLEAN DEFAULT FALSE",
            "regime": "VARCHAR(8) DEFAULT 'vat'",
        },
    )
    # Regime discriminator on documents (existing rows are all VAT).
    ensure_columns("documents", {"regime": "VARCHAR(8) DEFAULT 'vat'"})
    # VAT311 refund application stored on a VAT201 return.
    ensure_columns("vat201_returns", {"refund311_json": "TEXT"})
    # Soft-delete columns on the archive (existing rows default to not-deleted).
    ensure_columns("archive_files", {"deleted_at": "TIMESTAMP", "deleted_by": "VARCHAR(255)"})
    # SME-validation gate on effective-dated rules.
    ensure_columns("vat_rule_versions", {"requires_validation": "BOOLEAN DEFAULT FALSE"})
    # Seed the first admin from configured credentials (no-op if users already exist).
    from .auth.service import bootstrap_admin
    from .core.database import SessionLocal
    from .fta.seed import seed_fta

    with SessionLocal() as db:
        bootstrap_admin(db, settings.admin_email, settings.admin_password)
        # Seed official FTA sources + effective-dated rules on first boot (idempotent).
        try:
            seed_fta(db)
        except Exception:
            # Seeding is best-effort; a monitored source being unreachable at
            # boot must never block the app from starting.
            pass
    yield


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=(
        "AI-powered UAE VAT Compliance Platform API. Verdicts are produced by a "
        "deterministic rule engine grounded in Federal Decree-Law No. 8 of 2017 and its "
        "Executive Regulation."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth endpoints are public; everything else requires a valid session (when
# AUTH_ENABLED — the default). With auth disabled (tests/dev) the guard passes through.
app.include_router(auth_router)

_auth = [Depends(get_current_user)]
app.include_router(review_router, dependencies=_auth)
app.include_router(assistant_router, dependencies=_auth)
app.include_router(knowledge_router, dependencies=_auth)
app.include_router(ai_router, dependencies=_auth)
app.include_router(vat201_router, dependencies=_auth)
app.include_router(ct_router, dependencies=_auth)
app.include_router(archive_router, dependencies=_auth)
app.include_router(fta_router, dependencies=_auth)


@app.get("/health", tags=["system"])
def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "version": __version__, "env": settings.app_env}


@app.post("/api/review", response_model=ReviewResult, tags=["review"], dependencies=_auth)
def review(invoice: Invoice) -> ReviewResult:
    """Run the UAE VAT rule engine against a structured invoice."""
    return review_invoice(invoice)
