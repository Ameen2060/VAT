"""User persistence + authentication helpers."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..models import AuthAudit, PasswordResetToken, User
from .security import generate_reset_token, hash_password, hash_token, verify_password


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.strip().lower()))


def count_users(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User)) or 0


def create_user(
    db: Session, *, email: str, password: str, role: str = "reviewer", full_name: str | None = None
) -> User:
    user = User(
        email=email.strip().lower(),
        password_hash=hash_password(password),
        role=role,
        full_name=full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_credentials(
    db: Session,
    user: User,
    *,
    new_email: str | None = None,
    new_password: str | None = None,
    full_name: str | None = None,
) -> User:
    """Update the user's login details in place. Caller must have verified identity."""
    if new_email is not None:
        user.email = new_email.strip().lower()
    if full_name is not None:
        user.full_name = full_name.strip() or None
    if new_password:
        user.password_hash = hash_password(new_password)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = get_by_email(db, email)
    if user and user.is_active and verify_password(password, user.password_hash):
        return user
    return None


def bootstrap_admin(db: Session, email: str, password: str) -> None:
    """Create the first admin from configured credentials if there are no users yet."""
    if email and password and count_users(db) == 0:
        create_user(db, email=email, password=password, role="admin", full_name="Administrator")


# ── Password reset ────────────────────────────────────────────────────────────
def log_auth_event(
    db: Session, event: str, *, user_email: str | None = None, actor_email: str | None = None,
    detail: str | None = None, ip: str | None = None,
) -> None:
    db.add(AuthAudit(event=event, user_email=user_email, actor_email=actor_email,
                     detail=detail, ip=ip))
    db.commit()


# Simple in-memory rate limiter (per key). Fine for a single instance; swap for Redis at scale.
_reset_hits: dict[str, list[float]] = {}


def rate_limited(key: str, max_per_hour: int) -> bool:
    now = time.time()
    window = now - 3600
    hits = [t for t in _reset_hits.get(key, []) if t > window]
    hits.append(now)
    _reset_hits[key] = hits
    return len(hits) > max_per_hour


def create_reset_token(db: Session, user: User, ttl_minutes: int) -> str:
    """Invalidate any prior tokens for the user and issue a fresh single-use token."""
    db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
    raw = generate_reset_token()
    db.add(PasswordResetToken(
        user_id=user.id,
        token_hash=hash_token(raw),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes),
    ))
    db.commit()
    return raw


def reset_password_with_token(db: Session, raw_token: str, new_password: str) -> User | None:
    """Consume a valid token, set the new password, and invalidate all reset tokens."""
    rec = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(raw_token))
    )
    if not rec or rec.used:
        return None
    expires = rec.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        return None
    user = db.get(User, rec.user_id)
    if not user:
        return None
    user.password_hash = hash_password(new_password)   # invalidates the previous password
    # Invalidate this and every other reset token for the user.
    db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
    db.commit()
    db.refresh(user)
    return user
