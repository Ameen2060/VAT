"""Authentication endpoints: register, login, current user."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import service
from ..auth.deps import get_current_user, get_optional_user, require_admin
from ..auth.security import create_access_token
from ..core.config import get_settings
from ..core.database import get_db
from ..models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])
_VALID_ROLES = {"admin", "reviewer", "viewer"}


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str | None = None
    role: str = "reviewer"


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str | None
    role: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


def _user_out(u: User) -> UserOut:
    return UserOut(id=u.id, email=u.email, full_name=u.full_name, role=u.role)


def _issue_token(u: User) -> TokenResponse:
    s = get_settings()
    token = create_access_token(
        subject=u.id, role=u.role, secret=s.secret_key,
        algorithm=s.jwt_algorithm, ttl_minutes=s.access_token_ttl_minutes,
    )
    return TokenResponse(access_token=token, user=_user_out(u))


@router.post("/register", response_model=UserOut)
def register(
    body: RegisterRequest,
    db: Session = Depends(get_db),
    current: User | None = Depends(get_optional_user),
) -> UserOut:
    """Create a user. The FIRST user (empty DB) becomes admin with no auth required;
    afterwards, only an admin may create users."""
    if body.role not in _VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Allowed: {_VALID_ROLES}")
    first_user = service.count_users(db) == 0
    if not first_user and (current is None or current.role != "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    if service.get_by_email(db, body.email):
        raise HTTPException(status_code=409, detail="Email already registered")
    role = "admin" if first_user else body.role
    user = service.create_user(
        db, email=body.email, password=body.password, role=role, full_name=body.full_name
    )
    return _user_out(user)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = service.authenticate(db, body.email, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password"
        )
    return _issue_token(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return _user_out(user)


class UpdateAccountRequest(BaseModel):
    current_password: str
    new_email: str | None = None
    new_password: str | None = None
    full_name: str | None = None


@router.patch("/account", response_model=TokenResponse)
def update_account(
    body: UpdateAccountRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Change the signed-in user's own login details (email / password / name).

    The current password is required to authorise the change. A fresh token is
    returned so the client stays signed in with the updated identity.
    """
    if not service.verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect")

    new_email = body.new_email.strip().lower() if body.new_email else None
    if new_email and new_email != user.email:
        if "@" not in new_email or "." not in new_email:
            raise HTTPException(status_code=400, detail="Enter a valid email address")
        existing = service.get_by_email(db, new_email)
        if existing and existing.id != user.id:
            raise HTTPException(status_code=409, detail="That email is already in use")
    else:
        new_email = None

    if body.new_password is not None and len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")

    updated = service.update_credentials(
        db, user,
        new_email=new_email,
        new_password=body.new_password or None,
        full_name=body.full_name,
    )
    return _issue_token(updated)


class AdminUserCreate(RegisterRequest):
    pass


@router.get("/users", response_model=list[UserOut])
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[UserOut]:
    from sqlalchemy import select

    return [_user_out(u) for u in db.scalars(select(User).order_by(User.created_at))]
