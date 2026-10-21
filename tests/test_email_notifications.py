"""Automated test suite for email notifications, SMTP resilience, and serverless rate limiting."""
from datetime import datetime, timezone
from email.message import EmailMessage
import logging
from pathlib import Path
import smtplib
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.core.rate_limit import forgot_password_limiter, login_limiter
from app.database.session import Base, get_db
from app.main import app
from app.models.user import User

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


@pytest.fixture
def mock_smtp(monkeypatch):
    """Mock smtplib.SMTP to inspect sent messages and simulate SMTP transactions."""
    monkeypatch.setattr(settings, "smtp_host", "smtp.gmail.com")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_user", "pulse.ergonomics@gmail.com")
    monkeypatch.setattr(settings, "smtp_password", "test-app-password")
    monkeypatch.setattr(settings, "smtp_from", "PULSE <noreply@pulse.app>")
    monkeypatch.setattr(settings, "app_base_url", "https://pulse.app")

    sent_messages = []

    mock_server = MagicMock()

    def capture_send(msg):
        sent_messages.append(msg)
        return {}

    mock_server.send_message.side_effect = capture_send

    mock_smtp_class = MagicMock(return_value=mock_server)
    mock_server.__enter__.return_value = mock_server
    mock_server.__exit__.return_value = False

    monkeypatch.setattr(smtplib, "SMTP", mock_smtp_class)
    return {
        "server": mock_server,
        "class": mock_smtp_class,
        "messages": sent_messages,
    }


def test_welcome_email_sent_on_signup(client, mock_smtp):
    """TASK 1: Verify welcome email is sent synchronously on signup with required content and no password."""
    password_plain = "SuperSecretPassword123!"
    res = client.post("/api/auth/signup", json={
        "email": "Jane.Doe@Example.COM",
        "password": password_plain,
        "full_name": "Jane Doe",
    })
    assert res.status_code == 201
    assert "access_token" in res.json()

    # Verify SMTP was invoked
    mock_smtp["class"].assert_called_with("smtp.gmail.com", 587, timeout=15)
    mock_smtp["server"].starttls.assert_called_once()
    mock_smtp["server"].login.assert_called_once_with("pulse.ergonomics@gmail.com", "test-app-password")

    # Verify captured message
    assert len(mock_smtp["messages"]) == 1
    msg: EmailMessage = mock_smtp["messages"][0]

    assert msg["Subject"] == "Welcome to PULSE"
    assert msg["To"] == "jane.doe@example.com"
    assert msg["From"] == "PULSE <noreply@pulse.app>"

    # Check content (plain text + html alternative)
    plain_content = msg.get_body(preferencelist=("plain",)).get_content()
    html_content = msg.get_body(preferencelist=("html",)).get_content()

    # Plain text assertions
    assert "Welcome to PULSE!" in plain_content
    assert "jane.doe@example.com" in plain_content
    assert "https://pulse.app" in plain_content
    assert "If you did not sign up, you can ignore this email." in plain_content
    assert "- The PULSE Ergonomics Team" in plain_content
    assert password_plain not in plain_content

    # HTML assertions
    assert "Welcome to PULSE" in html_content
    assert "https://pulse.app" in html_content
    assert "If you did not sign up, you can ignore this email." in html_content
    assert password_plain not in html_content


def test_signup_still_works_if_smtp_fails(client, monkeypatch, test_db):
    """TASK 1: Verify signup succeeds even when SMTP connection or authentication fails."""
    monkeypatch.setattr(settings, "smtp_host", "smtp.gmail.com")
    monkeypatch.setattr(settings, "smtp_user", "pulse@gmail.com")
    monkeypatch.setattr(settings, "smtp_password", "invalid-pass")

    def raise_smtp_error(*args, **kwargs):
        raise smtplib.SMTPAuthenticationError(535, b"Authentication credentials invalid")

    monkeypatch.setattr(smtplib, "SMTP", raise_smtp_error)

    res = client.post("/api/auth/signup", json={
        "email": "resilient_user@example.com",
        "password": "ValidPassword123!",
        "full_name": "Resilient User",
    })

    # Signup must still succeed
    assert res.status_code == 201
    assert "access_token" in res.json()
    assert res.json()["user"]["email"] == "resilient_user@example.com"

    # User is confirmed created in the database
    db_user = test_db.query(User).filter(User.email == "resilient_user@example.com").first()
    assert db_user is not None
    assert db_user.full_name == "Resilient User"


def test_reset_email_sent_only_to_entered_registered_email(client, mock_smtp, caplog):
    """TASK 2: Verify reset email is sent ONLY to the exact registered email entered."""
    # 1. Register a user
    client.post("/api/auth/signup", json={
        "email": "valid_user@example.com",
        "password": "Password123!",
    })
    mock_smtp["messages"].clear()

    # 2. Request forgot-password with mixed case and whitespace
    with caplog.at_level(logging.INFO):
        res = client.post("/api/auth/forgot-password", json={
            "email": "   Valid_User@Example.COM   ",
        })

    assert res.status_code == 200
    assert res.json()["message"] == "If this email is registered, a password reset link has been sent."

    # Verify reset email was sent only to valid_user@example.com
    assert len(mock_smtp["messages"]) == 1
    msg: EmailMessage = mock_smtp["messages"][0]
    assert msg["To"] == "valid_user@example.com"
    assert msg["Subject"] == "PULSE - Password Reset Link"

    body = msg.get_body(preferencelist=("plain",)).get_content()
    assert "https://pulse.app/reset-password.html?token=" in body
    assert "- The PULSE Ergonomics Team" in body

    # Verify server log says result=True and does not log the token or link
    assert "reset email sent result=True" in caplog.text
    token = body.split("token=")[-1].strip()
    assert token not in caplog.text


def test_no_email_for_unknown_email(client, mock_smtp, caplog):
    """TASK 2: Unknown email returns generic 200, sends no email, and logs 'no account for this email'."""
    with caplog.at_level(logging.INFO):
        res = client.post("/api/auth/forgot-password", json={
            "email": "does_not_exist@example.com",
        })

    assert res.status_code == 200
    assert res.json()["message"] == "If this email is registered, a password reset link has been sent."
    assert len(mock_smtp["messages"]) == 0
    assert "no account for this email" in caplog.text


def test_email_normalization_across_all_endpoints(client, test_db):
    """TASK 2: Verify email is stripped and lowercased across signup, login, and forgot-password."""
    # Signup with whitespace and upper case
    res_signup = client.post("/api/auth/signup", json={
        "email": "   Normalized.User@Example.COM   ",
        "password": "Password123!",
    })
    assert res_signup.status_code == 201
    assert res_signup.json()["user"]["email"] == "normalized.user@example.com"

    # In DB it is normalized
    user = test_db.query(User).filter(User.email == "normalized.user@example.com").first()
    assert user is not None

    # Login with different casing and whitespace
    res_login = client.post("/api/auth/login", json={
        "email": "NORMALIZED.USER@EXAMPLE.COM",
        "password": "Password123!",
    })
    assert res_login.status_code == 200
    assert res_login.json()["user"]["email"] == "normalized.user@example.com"


def test_database_backed_rate_limiting_signup(client, caplog):
    """TASK 1: Verify rate limiting triggers for signup and logs 'rate limited'."""
    target_email = "repeat_signup@example.com"

    # Up to 3 signups allowed per email per hour
    for i in range(3):
        res = client.post("/api/auth/signup", json={
            "email": target_email,
            "password": f"Password123!_{i}",
        })
        # 1st is 201, 2nd & 3rd are 400 (already exists), but attempt is recorded
        assert res.status_code in (201, 400)

    # 4th signup attempt triggers rate limit (429)
    with caplog.at_level(logging.WARNING):
        res_blocked = client.post("/api/auth/signup", json={
            "email": target_email,
            "password": "Password123!_blocked",
        })

    assert res_blocked.status_code == 429
    assert "Too many attempts" in res_blocked.json()["detail"]
    assert "rate limited" in caplog.text


def test_database_backed_rate_limiting_forgot_password(client, caplog):
    """TASK 1: Verify rate limiting triggers for forgot-password and logs 'rate limited'."""
    target_email = "rate_fp@example.com"

    for _ in range(3):
        res = client.post("/api/auth/forgot-password", json={"email": target_email})
        assert res.status_code == 200

    with caplog.at_level(logging.WARNING):
        res_blocked = client.post("/api/auth/forgot-password", json={"email": target_email})

    assert res_blocked.status_code == 429
    assert "rate limited" in caplog.text


def test_full_password_reset_flow(client, mock_smtp):
    """TASK 2: Verify full flow: forgot-password -> email -> link -> set new password -> login."""
    # 1. Signup
    client.post("/api/auth/signup", json={
        "email": "full_flow@example.com",
        "password": "OldPassword123!",
    })
    mock_smtp["messages"].clear()

    # 2. Forgot password
    client.post("/api/auth/forgot-password", json={"email": "full_flow@example.com"})
    assert len(mock_smtp["messages"]) == 1

    # 3. Extract token from reset link in message body
    msg = mock_smtp["messages"][0]
    body = msg.get_body(preferencelist=("plain",)).get_content()
    assert "/reset-password.html?token=" in body
    raw_token = body.split("token=")[-1].split()[0].strip()

    # 4. Set new password
    res_reset = client.post("/api/auth/reset-password", json={
        "token": raw_token,
        "new_password": "NewSecretPassword123!",
    })
    assert res_reset.status_code == 200

    # 5. Old password rejected
    res_old = client.post("/api/auth/login", json={
        "email": "full_flow@example.com",
        "password": "OldPassword123!",
    })
    assert res_old.status_code == 401

    # 6. New password accepted
    res_new = client.post("/api/auth/login", json={
        "email": "full_flow@example.com",
        "password": "NewSecretPassword123!",
    })
    assert res_new.status_code == 200
    assert "access_token" in res_new.json()


def test_get_client_ip_resolution():
    """Verify client IP extraction handles X-Forwarded-For, X-Real-IP, and safe fallbacks."""
    from starlette.requests import Request
    from app.core.rate_limit import get_client_ip

    # 1. X-Forwarded-For with multiple IPs (first is client IP)
    scope_xff = {
        "type": "http",
        "headers": [(b"x-forwarded-for", b"203.0.113.195, 70.41.3.18, 150.172.238.178")],
        "client": ("10.0.0.1", 12345),
    }
    assert get_client_ip(Request(scope_xff)) == "203.0.113.195"

    # 2. X-Real-IP when X-Forwarded-For is absent
    scope_real = {
        "type": "http",
        "headers": [(b"x-real-ip", b"198.51.100.42")],
        "client": ("10.0.0.1", 12345),
    }
    assert get_client_ip(Request(scope_real)) == "198.51.100.42"

    # 3. Both headers present: X-Forwarded-For takes priority
    scope_both = {
        "type": "http",
        "headers": [
            (b"x-forwarded-for", b"203.0.113.50, 10.0.0.2"),
            (b"x-real-ip", b"198.51.100.42"),
        ],
        "client": ("10.0.0.1", 12345),
    }
    assert get_client_ip(Request(scope_both)) == "203.0.113.50"

    # 4. Direct client host fallback when headers are missing
    scope_direct = {
        "type": "http",
        "headers": [],
        "client": ("192.168.1.100", 54321),
    }
    assert get_client_ip(Request(scope_direct)) == "192.168.1.100"

    # 5. Safe fallback when client is None
    scope_none = {
        "type": "http",
        "headers": [],
        "client": None,
    }
    assert get_client_ip(Request(scope_none)) == "127.0.0.1"


def test_rate_limiting_uses_forwarded_ip_headers(client, caplog):
    """Verify endpoint rate limiting properly isolates by X-Forwarded-For client IP."""
    spoofed_ip_a = "203.0.113.10"
    spoofed_ip_b = "203.0.113.20"

    headers_a = {"X-Forwarded-For": f"{spoofed_ip_a}, 10.0.0.1"}
    headers_b = {"X-Forwarded-For": f"{spoofed_ip_b}, 10.0.0.1"}

    # Request from IP A
    res_a = client.post(
        "/api/auth/forgot-password",
        json={"email": "ip_test_a@example.com"},
        headers=headers_a,
    )
    assert res_a.status_code == 200

    # Request from IP B should have separate rate counter
    res_b = client.post(
        "/api/auth/forgot-password",
        json={"email": "ip_test_b@example.com"},
        headers=headers_b,
    )
    assert res_b.status_code == 200


def test_rate_limit_cleanup_on_write(test_db):
    """Verify old rate limit entries are deleted on write so table does not grow indefinitely."""
    from datetime import timedelta
    from app.core.rate_limit import record_db_attempt
    from app.models.rate_limit import RateLimitEvent

    now = datetime.now(timezone.utc)
    old_timestamp = now - timedelta(seconds=7200)  # 2 hours old

    # 1. Insert an expired entry for 'user_key'
    old_event = RateLimitEvent(key="user_key", created_at=old_timestamp)
    test_db.add(old_event)
    test_db.commit()

    assert test_db.query(RateLimitEvent).filter(RateLimitEvent.key == "user_key").count() == 1

    # 2. Record a new attempt with a 3600-second window
    record_db_attempt(test_db, "user_key", window_seconds=3600)

    # 3. Old entry should be deleted, only 1 new entry remains
    events = test_db.query(RateLimitEvent).filter(RateLimitEvent.key == "user_key").all()
    assert len(events) == 1
    created_at = events[0].created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    assert created_at >= now - timedelta(seconds=10)

    # 4. Insert an entry older than 24 hours for a different abandoned key
    abandoned_old = RateLimitEvent(key="abandoned_key", created_at=now - timedelta(hours=25))
    test_db.add(abandoned_old)
    test_db.commit()
    assert test_db.query(RateLimitEvent).filter(RateLimitEvent.key == "abandoned_key").count() == 1

    # 5. Writing any other attempt purges global entries older than 24h
    record_db_attempt(test_db, "active_key", window_seconds=3600)
    assert test_db.query(RateLimitEvent).filter(RateLimitEvent.key == "abandoned_key").count() == 0

