"""Automated test suite for Forgot Password & Password Reset flows."""
import hashlib
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND_DIR))

from app.core.rate_limit import forgot_password_limiter, login_limiter
from app.database.session import Base, get_db
from app.main import app
from app.models.password_reset_token import PasswordResetToken
from app.services import email_service

TEST_DB_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="function")
def test_db():
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client(test_db):
    forgot_password_limiter.clear()
    login_limiter.clear()

    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    forgot_password_limiter.clear()
    login_limiter.clear()


@pytest.fixture(autouse=True)
def mock_email(monkeypatch):
    """Ensure no real emails or network requests are ever made during testing."""
    mock_send = MagicMock(return_value=True)
    monkeypatch.setattr("app.api.auth.send_password_reset_email", mock_send)
    monkeypatch.setattr(email_service, "send_password_reset_email", mock_send)
    return mock_send


def test_forgot_password_malformed_email(client):
    """Verify that a malformed email on forgot-password returns 422 with clear message."""
    res = client.post("/api/auth/forgot-password", json={
        "email": "not-a-valid-email",
    })
    assert res.status_code == 422
    assert res.json()["detail"] == "Enter a valid email address"


def test_forgot_password_unknown_email(client, mock_email):
    """Verify unknown email returns 200 with generic message and does not send an email."""
    res = client.post("/api/auth/forgot-password", json={
        "email": "ghost_user@example.com",
    })
    assert res.status_code == 200
    assert res.json()["message"] == "If this email is registered, a password reset link has been sent."
    assert mock_email.call_count == 0


def test_forgot_password_known_email(client, test_db, mock_email):
    """Verify known email returns 200, persists sha256 token in DB, and dispatches email."""
    # 1. Register a user
    client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "InitialPassword123!",
    })

    # 2. Request forgot password
    res = client.post("/api/auth/forgot-password", json={
        "email": "alice@example.com",
    })
    assert res.status_code == 200
    assert res.json()["message"] == "If this email is registered, a password reset link has been sent."
    assert mock_email.call_count == 1

    # 3. Check parameters passed to email service
    recipient, reset_link = mock_email.call_args[0]
    assert recipient == "alice@example.com"
    assert "/reset-password.html?token=" in reset_link
    raw_token = reset_link.split("token=")[-1]
    assert len(raw_token) > 20

    # 4. Verify token in database is hashed with sha256
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    db_token = test_db.query(PasswordResetToken).filter(
        PasswordResetToken.token_hash == token_hash
    ).first()
    assert db_token is not None
    assert db_token.used_at is None
    assert db_token.token_hash != raw_token


def test_forgot_password_rate_limiting(client):
    """Verify rate limit triggers after 3 requests in an hour for the same email (HTTP 429)."""
    target_email = "rate_tester@example.com"

    for _ in range(3):
        res = client.post("/api/auth/forgot-password", json={"email": target_email})
        assert res.status_code == 200

    res_blocked = client.post("/api/auth/forgot-password", json={"email": target_email})
    assert res_blocked.status_code == 429
    assert "Too many attempts" in res_blocked.json()["detail"]


def test_reset_password_valid_token_updates_password_and_login(client, mock_email):
    """Verify valid token updates password, invalidates old credentials, and marks token used."""
    # 1. Register user
    client.post("/api/auth/signup", json={
        "email": "bob@example.com",
        "password": "OldPassword123!",
    })

    # 2. Request reset
    client.post("/api/auth/forgot-password", json={"email": "bob@example.com"})
    reset_link = mock_email.call_args[0][1]
    raw_token = reset_link.split("token=")[-1]

    # 3. Reset password
    res_reset = client.post("/api/auth/reset-password", json={
        "token": raw_token,
        "new_password": "NewSecretPassword123!",
    })
    assert res_reset.status_code == 200
    assert res_reset.json()["message"] == "Password updated. You can now sign in."

    # 4. Old password fails
    res_old_login = client.post("/api/auth/login", json={
        "email": "bob@example.com",
        "password": "OldPassword123!",
    })
    assert res_old_login.status_code == 401
    assert res_old_login.json()["detail"] == "Invalid email or password"

    # 5. New password succeeds
    res_new_login = client.post("/api/auth/login", json={
        "email": "bob@example.com",
        "password": "NewSecretPassword123!",
    })
    assert res_new_login.status_code == 200
    assert "access_token" in res_new_login.json()


def test_reset_password_used_token_fails(client, mock_email):
    """Verify reset-password with already used token fails with HTTP 400."""
    client.post("/api/auth/signup", json={
        "email": "charlie@example.com",
        "password": "Password123!",
    })
    client.post("/api/auth/forgot-password", json={"email": "charlie@example.com"})
    raw_token = mock_email.call_args[0][1].split("token=")[-1]

    # First reset succeeds
    res1 = client.post("/api/auth/reset-password", json={
        "token": raw_token,
        "new_password": "NewPassword123!",
    })
    assert res1.status_code == 200

    # Second reset with same token fails
    res2 = client.post("/api/auth/reset-password", json={
        "token": raw_token,
        "new_password": "AnotherPassword123!",
    })
    assert res2.status_code == 400
    assert res2.json()["detail"] == "Invalid or expired reset link"


def test_reset_password_expired_token_fails(client, test_db, mock_email):
    """Verify reset-password with expired token fails with HTTP 400."""
    client.post("/api/auth/signup", json={
        "email": "dave@example.com",
        "password": "Password123!",
    })
    client.post("/api/auth/forgot-password", json={"email": "dave@example.com"})
    raw_token = mock_email.call_args[0][1].split("token=")[-1]

    # Expire the token in the database
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    db_token = test_db.query(PasswordResetToken).filter(
        PasswordResetToken.token_hash == token_hash
    ).first()
    assert db_token is not None
    db_token.expires_at = datetime.now(timezone.utc) - timedelta(hours=2)
    test_db.commit()

    # Attempt reset
    res = client.post("/api/auth/reset-password", json={
        "token": raw_token,
        "new_password": "NewPassword123!",
    })
    assert res.status_code == 400
    assert res.json()["detail"] == "Invalid or expired reset link"


def test_reset_password_short_password_fails(client, mock_email):
    """Verify reset-password with password < 8 characters returns HTTP 422."""
    client.post("/api/auth/signup", json={
        "email": "eve@example.com",
        "password": "Password123!",
    })
    client.post("/api/auth/forgot-password", json={"email": "eve@example.com"})
    raw_token = mock_email.call_args[0][1].split("token=")[-1]

    res = client.post("/api/auth/reset-password", json={
        "token": raw_token,
        "new_password": "short",
    })
    assert res.status_code == 422
    assert res.json()["detail"] == "Password must be at least 8 characters long"


def test_reset_password_invalid_token_fails(client):
    """Verify reset-password with non-existent token returns HTTP 400."""
    res = client.post("/api/auth/reset-password", json={
        "token": "unknown-nonexistent-token",
        "new_password": "ValidPassword123!",
    })
    assert res.status_code == 400
    assert res.json()["detail"] == "Invalid or expired reset link"
