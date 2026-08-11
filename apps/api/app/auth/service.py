"""User persistence + authentication helpers."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import User
from .security import hash_password, verify_password


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
