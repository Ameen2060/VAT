"""Tests for authentication: password hashing, JWT, and register/login endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.main import app


def test_password_hash_and_verify():
    h = hash_password("s3cret-pw")
    assert h.startswith("pbkdf2_sha256$")
    assert verify_password("s3cret-pw", h)
    assert not verify_password("wrong", h)
    # Two hashes of the same password differ (random salt).
    assert hash_password("s3cret-pw") != h


def test_jwt_roundtrip():
    token = create_access_token(
        subject="user-1", role="admin", secret="k3y", algorithm="HS256", ttl_minutes=5
    )
    payload = decode_access_token(token, "k3y", "HS256")
    assert payload["sub"] == "user-1"
    assert payload["role"] == "admin"


def test_register_first_admin_then_login():
    with TestClient(app) as client:
        # First user in an empty DB becomes admin.
        reg = client.post(
            "/api/auth/register",
            json={"email": "owner@keturah.ae", "password": "pw-12345678"},
        )
        assert reg.status_code == 200, reg.text
        assert reg.json()["role"] == "admin"

        # Login returns a bearer token + the user.
        login = client.post(
            "/api/auth/login",
            json={"email": "owner@keturah.ae", "password": "pw-12345678"},
        )
        assert login.status_code == 200, login.text
        body = login.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]
        assert body["user"]["email"] == "owner@keturah.ae"

        # Wrong password is rejected.
        bad = client.post(
            "/api/auth/login",
            json={"email": "owner@keturah.ae", "password": "nope"},
        )
        assert bad.status_code == 401
