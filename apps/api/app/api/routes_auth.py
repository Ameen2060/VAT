"""Authentication endpoints: register, login, current user."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import service
from ..auth.deps import get_current_user, get_optional_user, require_admin
from ..auth.security import create_access_token, validate_password_strength
from ..core.config import get_settings
from ..core.database import get_db
from ..models import AuthAudit, User

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

    if body.new_password:
        err = validate_password_strength(body.new_password)
        if err:
            raise HTTPException(status_code=400, detail=err)

    updated = service.update_credentials(
        db, user,
        new_email=new_email,
        new_password=body.new_password or None,
        full_name=body.full_name,
    )
    if body.new_password:
        service.log_auth_event(db, "password_changed", user_email=updated.email,
                               actor_email=updated.email, detail="Changed via account settings")
    return _issue_token(updated)


# ── Password reset / forgot password ─────────────────────────────────────────
_GENERIC_MSG = "If an account with that email exists, a password reset link has been sent."


class ForgotPasswordRequest(BaseModel):
    email: str


class ForgotPasswordResponse(BaseModel):
    message: str
    # DEV/DEMO only: present when EXPOSE_RESET_LINK is enabled (no SMTP configured).
    reset_url: str | None = None


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


def _reset_url(token: str) -> str:
    base = get_settings().app_base_url.rstrip("/")
    return f"{base}/reset-password?token={token}"


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(
    body: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)
) -> ForgotPasswordResponse:
    """Start password recovery. Always returns the same generic message so account
    existence is never revealed. Rate-limited per email + client IP."""
    s = get_settings()
    email = (body.email or "").strip().lower()
    ip = request.client.host if request.client else None

    if service.rate_limited(f"forgot:{email}:{ip}", s.reset_max_requests_per_hour):
        service.log_auth_event(db, "forgot_request", user_email=email, ip=ip, detail="rate limited")
        raise HTTPException(status_code=429, detail="Too many reset requests. Please try again later.")

    user = service.get_by_email(db, email)
    reset_url: str | None = None
    if user and user.is_active:
        raw = service.create_reset_token(db, user, s.reset_token_ttl_minutes)
        url = _reset_url(raw)
        # Delivery: email via SMTP if configured; otherwise the link is available in server
        # logs (and, in dev/demo, optionally in the response).
        print(f"[password-reset] link for {email}: {url}")
        if s.expose_reset_link:
            reset_url = url
        service.log_auth_event(db, "forgot_request", user_email=email, ip=ip, detail="token issued")
    else:
        service.log_auth_event(db, "forgot_request", user_email=email, ip=ip, detail="no account")

    return ForgotPasswordResponse(message=_GENERIC_MSG, reset_url=reset_url)


@router.post("/reset-password", response_model=TokenResponse)
def reset_password(
    body: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)
) -> TokenResponse:
    """Complete recovery: set a new password using a valid, unexpired token. The current
    password is NOT required here (this is the verified recovery path)."""
    err = validate_password_strength(body.new_password)
    if err:
        raise HTTPException(status_code=400, detail=err)
    ip = request.client.host if request.client else None
    user = service.reset_password_with_token(db, body.token.strip(), body.new_password)
    if not user:
        service.log_auth_event(db, "reset_failed", ip=ip, detail="invalid or expired token")
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired. Request a new one.")
    service.log_auth_event(db, "reset_success", user_email=user.email, ip=ip)
    return _issue_token(user)  # sign the user in with the new password


class AdminResetResponse(BaseModel):
    user_email: str
    reset_url: str
    expires_minutes: int


@router.post("/users/{user_id}/reset-password", response_model=AdminResetResponse)
def admin_reset_password(
    user_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> AdminResetResponse:
    """Admin-initiated reset: issue a one-time reset link for a user WITHOUT viewing or
    changing their password. The admin hands the link to the user (or it is emailed)."""
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    s = get_settings()
    raw = service.create_reset_token(db, target, s.reset_token_ttl_minutes)
    service.log_auth_event(db, "admin_reset_initiated", user_email=target.email,
                           actor_email=getattr(admin, "email", None))
    return AdminResetResponse(
        user_email=target.email, reset_url=_reset_url(raw), expires_minutes=s.reset_token_ttl_minutes
    )


class AuthAuditOut(BaseModel):
    id: str
    event: str
    user_email: str | None
    actor_email: str | None
    detail: str | None
    created_at: str | None


@router.get("/audit", response_model=list[AuthAuditOut])
def auth_audit(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[AuthAuditOut]:
    """Security audit trail of password reset / change events (admin only)."""
    rows = db.execute(select(AuthAudit).order_by(AuthAudit.created_at.desc()).limit(300)).scalars()
    return [
        AuthAuditOut(id=a.id, event=a.event, user_email=a.user_email, actor_email=a.actor_email,
                     detail=a.detail, created_at=a.created_at.isoformat() if a.created_at else None)
        for a in rows
    ]


class AdminUserCreate(RegisterRequest):
    pass


@router.get("/users", response_model=list[UserOut])
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[UserOut]:
    from sqlalchemy import select

    return [_user_out(u) for u in db.scalars(select(User).order_by(User.created_at))]
