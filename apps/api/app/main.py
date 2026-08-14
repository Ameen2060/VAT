"""FastAPI application entrypoint.

Phase 0 exposes a health check and a working `/api/review` endpoint that runs the
deterministic VAT rule engine against a structured invoice. File upload, OCR and AI
extraction arrive in Phase 1 and will feed the same engine.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError

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
from .vat.rules import review_invoice
from .vat.schemas import Invoice, ReviewResult

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Create tables, run additive migrations, seed admin + FTA data (idempotent).
    # Never hard-fail startup: if the database is briefly unreachable, the app still
    # serves /health and retries initialization on the next cold start / request.
    from .core.bootstrap import init_db

    try:
        init_db()
    except Exception:  # noqa: BLE001
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


async def _database_unavailable(_: Request, __: Exception) -> JSONResponse:
    """Return a clear 503 (not a raw 500) when the database can't be reached — e.g.
    the managed Postgres is waking from idle, briefly restarting, or not attached. The
    frontend maps 503 to a friendly 'temporarily unavailable — retry' message and
    auto-retries, so a waking database is invisible to the user."""
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "The service database is momentarily unavailable (waking up or "
                "reconnecting). Please retry in a moment."
            )
        },
    )


# Both are connection-class SQLAlchemy errors; treat either as "retry", never a 500.
app.add_exception_handler(OperationalError, _database_unavailable)
app.add_exception_handler(InterfaceError, _database_unavailable)


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
