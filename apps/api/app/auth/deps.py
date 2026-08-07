"""FastAPI auth dependencies.

`get_current_user` accepts the JWT from either the `Authorization: Bearer` header
(fetch/XHR) OR a `?token=` query parameter — the latter lets browser-driven requests
that can't set headers (an <iframe> PDF preview, a download link) stay authenticated.

When AUTH_ENABLED is false (tests/local dev), a synthetic admin is returned so the API
works without tokens.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.database import get_db
from ..models import User
from .security import decode_access_token


def _token_from_request(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.query_params.get("token")


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    settings = get_settings()
    if not settings.auth_enabled:
        return User(id="dev", email="dev@local", password_hash="", role="admin", is_active=True)

    token = _token_from_request(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_access_token(token, settings.secret_key, settings.jwt_algorithm)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session"
        ) from e

    user = db.get(User, payload.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    """Like get_current_user but returns None instead of raising when unauthenticated."""
    settings = get_settings()
    if not settings.auth_enabled:
        return User(id="dev", email="dev@local", password_hash="", role="admin", is_active=True)
    token = _token_from_request(request)
    if not token:
        return None
    try:
        payload = decode_access_token(token, settings.secret_key, settings.jwt_algorithm)
    except Exception:  # noqa: BLE001
        return None
    user = db.get(User, payload.get("sub"))
    return user if (user and user.is_active) else None


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
