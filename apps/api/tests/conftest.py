"""Test configuration: point the app at a throwaway SQLite DB and temp storage
*before* the application modules import and build their engine.
"""

from __future__ import annotations

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="vat-test-")
# Forward slashes keep the SQLite URL valid on Windows.
_db_path = os.path.join(_tmp, "test.sqlite3").replace(os.sep, "/")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_db_path}")
os.environ.setdefault("STORAGE_BACKEND", "local")
os.environ.setdefault("LOCAL_STORAGE_DIR", os.path.join(_tmp, "storage"))
os.environ.setdefault("AI_PROVIDER", "none")  # offline stub — no key needed
os.environ.setdefault("AUTH_ENABLED", "false")  # pass-through auth in the general suite
os.environ.setdefault("ADMIN_EMAIL", "")  # no bootstrap admin in tests
os.environ.setdefault("ADMIN_PASSWORD", "")
