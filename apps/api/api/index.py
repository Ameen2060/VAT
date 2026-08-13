"""Vercel serverless entrypoint for the FastAPI backend.

Vercel's Python runtime serves the ASGI application exported as `app`. All routes are
rewritten to this single function (see vercel.json), so FastAPI does its own routing
for `/health`, `/api/*`, etc. The database is initialized once per cold start.
"""

import os
import sys

# Project root (apps/api) — make the `app` package importable regardless of cwd.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app  # noqa: E402  (ASGI app Vercel will serve)

# Create tables / seed on cold start. Wrapped so a transient DB hiccup at import time
# doesn't hard-fail every request in this container — FastAPI's lifespan also calls it.
try:
    from app.core.bootstrap import init_db

    init_db()
except Exception:  # noqa: BLE001
    pass
