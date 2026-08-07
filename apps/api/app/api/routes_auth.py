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


class AdminUserCreate(RegisterRequest):
    pass


@router.get("/users", response_model=list[UserOut])
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[UserOut]:
    from sqlalchemy import select

    return [_user_out(u) for u in db.scalars(select(User).order_by(User.created_at))]
