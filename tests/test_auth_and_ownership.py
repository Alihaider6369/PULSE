"""Automated test suite for User Authentication, Ownership Enforcement, and Idempotent Sync."""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

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
from app.core.security import verify_password
from app.database.session import Base, get_db
from app.models.password_reset_token import PasswordResetToken
from app.main import app

# Isolated in-memory SQLite database for test execution
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
    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------- Authentication & Security Tests ----------------

def test_signup_and_password_hashing(client, test_db):
    """Verify signup creates user, hashes password with bcrypt, and generates JWT token."""
    res = client.post("/api/auth/signup", json={
        "email": "user_a@example.com",
        "password": "SecurePassword123!",
        "full_name": "User Alpha",
    })
    assert res.status_code == 201
    data = res.json()
    assert "access_token" in data
    assert data["user"]["email"] == "user_a@example.com"
    assert data["user"]["full_name"] == "User Alpha"

    # Verify password in DB is securely hashed, not plaintext
    from app.models.user import User
    user = test_db.query(User).filter(User.email == "user_a@example.com").first()
    assert user is not None
    assert user.hashed_password != "SecurePassword123!"
    assert user.hashed_password.startswith("$2b$") or user.hashed_password.startswith("$2a$")
    assert verify_password("SecurePassword123!", user.hashed_password) is True


def test_signup_validation_and_duplicate_prevention(client):
    """Verify email format check, password length check, and duplicate email rejection."""
    # 1. Short password (< 8 chars)
    res_short = client.post("/api/auth/signup", json={
        "email": "valid@example.com",
        "password": "short",
    })
    assert res_short.status_code == 422

    # 2. Invalid email format
    res_email = client.post("/api/auth/signup", json={
        "email": "not-an-email",
        "password": "ValidPassword123!",
    })
    assert res_email.status_code == 422

    # 3. Successful first registration
    res_ok = client.post("/api/auth/signup", json={
        "email": "test_dupe@example.com",
        "password": "ValidPassword123!",
    })
    assert res_ok.status_code == 201

    # 4. Duplicate registration attempt
    res_dupe = client.post("/api/auth/signup", json={
        "email": "test_dupe@example.com",
        "password": "AnotherPassword123!",
    })
    assert res_dupe.status_code == 400
    assert "already exists" in res_dupe.json()["detail"].lower()


def test_login_and_token_authentication(client):
    """Verify login with correct credentials returns valid JWT token."""
    # Create user
    client.post("/api/auth/signup", json={
        "email": "user_login@example.com",
        "password": "Password123!",
    })

    # Wrong password
    res_wrong = client.post("/api/auth/login", json={
        "email": "user_login@example.com",
        "password": "WrongPassword!",
    })
    assert res_wrong.status_code == 401

    # Correct password
    res_ok = client.post("/api/auth/login", json={
        "email": "user_login@example.com",
        "password": "Password123!",
    })
    assert res_ok.status_code == 200
    token = res_ok.json()["access_token"]

    # Test /api/auth/me
    headers = {"Authorization": f"Bearer {token}"}
    res_me = client.get("/api/auth/me", headers=headers)
    assert res_me.status_code == 200
    assert res_me.json()["email"] == "user_login@example.com"


# ---------------- Cross-User Access Isolation Tests ----------------

def test_cross_user_isolation(client):
    """Prove that User A cannot access, modify, or view User B's sessions and settings."""
    # Register User A
    res_a = client.post("/api/auth/signup", json={
        "email": "usera@example.com",
        "password": "UserAPassword123!",
    })
    token_a = res_a.json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Register User B
    res_b = client.post("/api/auth/signup", json={
        "email": "userb@example.com",
        "password": "UserBPassword123!",
    })
    token_b = res_b.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 1. User A starts a session
    res_sess_a = client.post(
        "/api/sessions/start",
        json={"session_code": "sess_alpha_123"},
        headers=headers_a,
    )
    assert res_sess_a.status_code == 201
    session_id_a = res_sess_a.json()["id"]

    # 2. User B lists sessions -> MUST NOT see User A's session
    res_b_list = client.get("/api/sessions", headers=headers_b)
    assert res_b_list.status_code == 200
    assert len(res_b_list.json()) == 0

    # 3. User B attempts to finalize User A's session -> Access denied / 404
    res_hack = client.post(
        f"/api/sessions/{session_id_a}/end",
        json={"good_seconds": 10.0, "poor_seconds": 10.0, "warning_count": 0},
        headers=headers_b,
    )
    assert res_hack.status_code == 404

    # 4. User A updates personal settings
    res_set_a = client.put(
        "/api/settings",
        json={
            "poor_posture_threshold_seconds": 45.0,
            "cooldown_seconds": 200.0,
            "warning_duration_seconds": 8.0,
            "sound_enabled": False,
            "min_confidence": 0.65,
        },
        headers=headers_a,
    )
    assert res_set_a.status_code == 200

    # 5. User B reads settings -> must remain default, unaffected by User A
    res_set_b = client.get("/api/settings", headers=headers_b)
    assert res_set_b.status_code == 200
    assert res_set_b.json()["poor_posture_threshold_seconds"] == 30.0  # Default value
    assert res_set_b.json()["sound_enabled"] is True


# ---------------- Idempotent Sync Tests ----------------

def test_idempotent_synchronization(client):
    """Verify that batch syncing multiple times creates zero duplicate sessions or events."""
    # Register User
    res = client.post("/api/auth/signup", json={
        "email": "syncer@example.com",
        "password": "SyncPassword123!",
    })
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    sync_payload = {
        "sessions": [
            {
                "client_uuid": "sync-uuid-session-001",
                "session_code": "code001",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "ended_at": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": 120.0,
                "good_seconds": 100.0,
                "poor_seconds": 20.0,
                "warning_count": 1,
                "awareness_score": 83.3,
                "events": [
                    {
                        "client_uuid": "sync-uuid-event-001",
                        "occurred_at": datetime.now(timezone.utc).isoformat(),
                        "posture_class": "poor_posture",
                        "confidence": 0.85,
                        "duration_seconds": 30.0,
                        "is_warning": True,
                    }
                ],
            }
        ]
    }

    # 1. First sync call
    res_sync_1 = client.post("/api/sessions/sync", json=sync_payload, headers=headers)
    assert res_sync_1.status_code == 200
    assert len(res_sync_1.json()["synced"]) == 1
    assert res_sync_1.json()["synced"][0]["client_uuid"] == "sync-uuid-session-001"

    # 2. Second sync call with exact same payload (simulating network retry)
    res_sync_2 = client.post("/api/sessions/sync", json=sync_payload, headers=headers)
    assert res_sync_2.status_code == 200
    assert len(res_sync_2.json()["synced"]) == 1

    # 3. Check session count: Exactly 1 session in total
    res_list = client.get("/api/sessions", headers=headers)
    assert res_list.status_code == 200
    assert len(res_list.json()) == 1
    assert res_list.json()[0]["client_uuid"] == "sync-uuid-session-001"


# ---------------- Safer Login Errors & Password Reset Tests ----------------

def test_safer_login_errors_and_rate_limiting(client, test_db):
    """Verify email format validation, timing-safe 401 error message, and 5-attempt rate limit."""
    login_limiter.clear()

    # 1. Invalid email format -> 422 "Enter a valid email address"
    res_bad_email = client.post("/api/auth/login", json={
        "email": "not-valid-email",
        "password": "ValidPassword123!",
    })
    assert res_bad_email.status_code == 422
    assert res_bad_email.json()["detail"] == "Enter a valid email address"

    # 2. Non-existent email -> 401 "Invalid email or password"
    res_unknown = client.post("/api/auth/login", json={
        "email": "unknown_user@example.com",
        "password": "RandomPassword123!",
    })
    assert res_unknown.status_code == 401
    assert res_unknown.json()["detail"] == "Invalid email or password"

    # 3. Create registered user
    client.post("/api/auth/signup", json={
        "email": "rate_limit_user@example.com",
        "password": "CorrectPassword123!",
    })

    # 4. Wrong password -> 401 "Invalid email or password"
    res_wrong = client.post("/api/auth/login", json={
        "email": "rate_limit_user@example.com",
        "password": "WrongPassword123!",
    })
    assert res_wrong.status_code == 401
    assert res_wrong.json()["detail"] == "Invalid email or password"

    # 5. Trigger rate limiter: attempt 2, 3, 4, 5 fail with 401
    for _ in range(4):
        res_fail = client.post("/api/auth/login", json={
            "email": "rate_limit_user@example.com",
            "password": "WrongPassword123!",
        })
        assert res_fail.status_code == 401

    # 6th attempt -> 429 Too many attempts
    res_blocked = client.post("/api/auth/login", json={
        "email": "rate_limit_user@example.com",
        "password": "WrongPassword123!",
    })
    assert res_blocked.status_code == 429
    assert "Too many attempts" in res_blocked.json()["detail"]

    # Clean up limiter
    login_limiter.clear()


def test_forgot_and_reset_password_flow(client, test_db, monkeypatch):
    """Verify forgot-password enumeration safety, background token creation, and reset flow."""
    import hashlib
    from unittest.mock import MagicMock
    from app.services import email_service

    forgot_password_limiter.clear()

    # Mock email sender so no real emails are ever sent
    mock_sender = MagicMock(return_value=True)
    monkeypatch.setattr("app.api.auth.send_password_reset_email", mock_sender)
    monkeypatch.setattr(email_service, "send_password_reset_email", mock_sender)

    # 1. Malformed email on forgot-password -> 422
    res_malformed = client.post("/api/auth/forgot-password", json={
        "email": "invalid-format",
    })
    assert res_malformed.status_code == 422
    assert res_malformed.json()["detail"] == "Enter a valid email address"

    # 2. Non-existent email -> 200 with standard message
    res_ghost = client.post("/api/auth/forgot-password", json={
        "email": "nonexistent_person@example.com",
    })
    assert res_ghost.status_code == 200
    assert res_ghost.json()["message"] == "If this email is registered, a password reset link has been sent."
    assert mock_sender.call_count == 0

    # 3. Register a real user
    client.post("/api/auth/signup", json={
        "email": "reset_user@example.com",
        "password": "OldPassword123!",
    })

    # 4. Request password reset for existing user -> 200 with exact same message
    res_exist = client.post("/api/auth/forgot-password", json={
        "email": "reset_user@example.com",
    })
    assert res_exist.status_code == 200
    assert res_exist.json()["message"] == "If this email is registered, a password reset link has been sent."
    assert mock_sender.call_count == 1

    # Extract sent reset link from mock call
    call_args = mock_sender.call_args[0]
    to_email, reset_link = call_args[0], call_args[1]
    assert to_email == "reset_user@example.com"
    assert "token=" in reset_link
    raw_token = reset_link.split("token=")[-1]

    # Verify token stored in DB is hashed with sha256 (raw token never stored)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    db_token = test_db.query(PasswordResetToken).filter(
        PasswordResetToken.token_hash == token_hash
    ).first()
    assert db_token is not None
    assert db_token.used_at is None
    assert db_token.token_hash != raw_token

    # 5. Reset password with invalid token -> 400
    res_bad_token = client.post("/api/auth/reset-password", json={
        "token": "fake-invalid-token",
        "new_password": "BrandNewPassword123!",
    })
    assert res_bad_token.status_code == 400
    assert res_bad_token.json()["detail"] == "Invalid or expired reset link"

    # 6. Reset password with short password (<8 chars) -> 422
    res_short = client.post("/api/auth/reset-password", json={
        "token": raw_token,
        "new_password": "short",
    })
    assert res_short.status_code == 422

    # 7. Successful password reset
    res_success = client.post("/api/auth/reset-password", json={
        "token": raw_token,
        "new_password": "BrandNewPassword123!",
    })
    assert res_success.status_code == 200
    assert res_success.json()["message"] == "Password updated. You can now sign in."

    # 8. Re-using same token fails -> 400
    res_reuse = client.post("/api/auth/reset-password", json={
        "token": raw_token,
        "new_password": "BrandNewPassword123!",
    })
    assert res_reuse.status_code == 400
    assert res_reuse.json()["detail"] == "Invalid or expired reset link"

    # 9. Login with old password fails
    res_old_login = client.post("/api/auth/login", json={
        "email": "reset_user@example.com",
        "password": "OldPassword123!",
    })
    assert res_old_login.status_code == 401

    # 10. Login with new password succeeds
    res_new_login = client.post("/api/auth/login", json={
        "email": "reset_user@example.com",
        "password": "BrandNewPassword123!",
    })
    assert res_new_login.status_code == 200
    assert "access_token" in res_new_login.json()
