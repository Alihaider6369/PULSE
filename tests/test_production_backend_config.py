"""Automated audit tests for PULSE Production Backend Configuration.

Verifies:
1. SECRET_KEY validation: missing, weak/placeholder, and short secrets fail safely in production/serverless.
2. DATABASE_URL validation: SQLite, localhost, and missing URLs are blocked in production/serverless.
3. PostgreSQL / Neon URL normalization to psycopg with sslmode=require.
4. Upstash Redis & Vercel KV environment variable alias choices.
5. Database connection error handling (graceful HTTP 503 via OperationalError handler).
6. Consistent JWT authentication token signing and verification using production settings.
"""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import Settings, settings
from app.core.security import create_access_token, decode_access_token
from app.main import app

STRONG_PROD_SECRET = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
NEON_DATABASE_URL = "postgresql://pulse_neon_user:secure_pass@ep-cool-frog-123456-pooler.us-east-2.aws.neon.tech/neondb"


# ---------------- 1. SECRET_KEY Security Audit ----------------


def test_secret_key_missing_fails():
    """Verify that a missing or empty SECRET_KEY raises a clear RuntimeError."""
    with patch.dict(os.environ, {"SECRET_KEY": "", "ENVIRONMENT": "development"}, clear=False):
        with pytest.raises(RuntimeError, match="SECRET_KEY environment variable is required"):
            Settings(secret_key="", environment="development")


def test_secret_key_weak_placeholder_fails():
    """Verify that common weak placeholder values for SECRET_KEY fail validation."""
    for weak_key in ["secret", "password", "changethis", "replace_with_cryptographically_secure_hex_string_min_64_chars"]:
        with pytest.raises(RuntimeError, match="SECRET_KEY cannot be a default or placeholder value"):
            Settings(secret_key=weak_key, environment="development")


def test_secret_key_short_in_production_fails():
    """Verify that secrets shorter than 32 characters are blocked in production mode."""
    short_key = "too-short-key-12345"
    with pytest.raises(RuntimeError, match="at least 32 characters long in production"):
        Settings(
            secret_key=short_key,
            environment="production",
            database_url=NEON_DATABASE_URL,
        )


def test_secret_key_short_on_vercel_fails():
    """Verify that secrets shorter than 32 characters are blocked when running on Vercel."""
    short_key = "short-key-under-32-chars"
    with patch.dict(os.environ, {"VERCEL": "1"}):
        with pytest.raises(RuntimeError, match="at least 32 characters long in production"):
            Settings(
                secret_key=short_key,
                database_url=NEON_DATABASE_URL,
            )


def test_secret_key_strong_in_production_succeeds():
    """Verify that a 64-character cryptographic hex secret is accepted in production."""
    cfg = Settings(
        secret_key=STRONG_PROD_SECRET,
        environment="production",
        database_url=NEON_DATABASE_URL,
    )
    assert cfg.secret_key == STRONG_PROD_SECRET


# ---------------- 2. DATABASE_URL Production & Vercel Audit ----------------


def test_database_url_sqlite_rejected_in_production():
    """Verify that SQLite URLs are strictly forbidden in production to prevent data loss."""
    with pytest.raises(RuntimeError, match="SQLite is not supported in production/serverless"):
        Settings(
            secret_key=STRONG_PROD_SECRET,
            environment="production",
            database_url="sqlite:///pulse_local.db",
        )


def test_database_url_sqlite_rejected_on_vercel():
    """Verify that SQLite URLs are strictly forbidden when VERCEL=1."""
    with patch.dict(os.environ, {"VERCEL": "1"}):
        with pytest.raises(RuntimeError, match="SQLite is not supported in production/serverless"):
            Settings(
                secret_key=STRONG_PROD_SECRET,
                database_url="sqlite:///:memory:",
            )


def test_database_url_localhost_rejected_in_production():
    """Verify that localhost/127.0.0.1 database URLs are blocked in production."""
    with pytest.raises(RuntimeError, match="remote managed PostgreSQL database"):
        Settings(
            secret_key=STRONG_PROD_SECRET,
            environment="production",
            database_url="postgresql+psycopg://pulse_user:password@localhost:5432/pulse_db",
        )


def test_database_url_missing_rejected_in_production():
    """Verify that an empty DATABASE_URL is blocked in production."""
    with pytest.raises(RuntimeError, match="DATABASE_URL environment variable is required"):
        Settings(
            secret_key=STRONG_PROD_SECRET,
            environment="production",
            database_url="",
        )


def test_database_url_neon_postgres_normalizes_with_ssl():
    """Verify that Neon PostgreSQL connection URLs are normalized to psycopg with sslmode=require."""
    cfg = Settings(
        secret_key=STRONG_PROD_SECRET,
        environment="production",
        database_url=NEON_DATABASE_URL,
    )
    norm = cfg.sync_database_url
    assert norm.startswith("postgresql+psycopg://")
    assert "sslmode=require" in norm
    assert "ep-cool-frog-123456-pooler.us-east-2.aws.neon.tech" in norm


# ---------------- 3. Upstash Redis & Vercel KV Alias Audit ----------------


def test_upstash_redis_env_variables_loaded():
    """Verify that UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN populate settings."""
    cfg = Settings(
        secret_key=STRONG_PROD_SECRET,
        upstash_redis_rest_url="https://direct-upstash.upstash.io",
        upstash_redis_rest_token="token_abc_123",
    )
    assert cfg.upstash_redis_rest_url == "https://direct-upstash.upstash.io"
    assert cfg.effective_upstash_url == "https://direct-upstash.upstash.io"
    assert cfg.effective_upstash_token == "token_abc_123"


def test_vercel_kv_alias_variables_loaded():
    """Verify that Vercel KV environment variables (KV_REST_API_URL/TOKEN, KV_URL) map to settings."""
    with patch.dict(os.environ, {
        "KV_REST_API_URL": "https://kv-alias.upstash.io",
        "KV_REST_API_TOKEN": "token_kv_alias",
        "KV_URL": "rediss://default:kvpass@kv-alias.upstash.io:6379",
    }):
        cfg = Settings(
            secret_key=STRONG_PROD_SECRET,
        )
        assert cfg.effective_upstash_url == "https://kv-alias.upstash.io"
        assert cfg.effective_upstash_token == "token_kv_alias"
        assert cfg.effective_redis_url == "rediss://default:kvpass@kv-alias.upstash.io:6379"


# ---------------- 4. Database Connection Operational Error Handling ----------------


def test_database_operational_error_returns_503():
    """Verify that when an OperationalError occurs, FastAPI returns HTTP 503 instead of 500."""
    from sqlalchemy.exc import OperationalError
    from app.database.session import get_db

    def failing_get_db():
        raise OperationalError("connection refused", {}, Exception("Neon pooler cold start timeout"))

    app.dependency_overrides[get_db] = failing_get_db
    try:
        client = TestClient(app)
        res = client.get("/api/sessions")
        assert res.status_code == 503
        data = res.json()
        assert "Database service is temporarily unavailable" in data["detail"]
    finally:
        app.dependency_overrides.clear()


# ---------------- 5. Authentication Configuration Consistency ----------------


def test_auth_token_roundtrip_with_production_settings():
    """Verify that JWT token generation and decoding match configured settings."""
    test_sub = "12345"
    token = create_access_token({"sub": test_sub, "email": "audit@pulse.internal"})
    payload = decode_access_token(token)

    assert payload is not None
    assert payload["sub"] == test_sub
    assert payload["email"] == "audit@pulse.internal"
    assert "exp" in payload

    # Tampered token fails
    assert decode_access_token(token + "tamper") is None
