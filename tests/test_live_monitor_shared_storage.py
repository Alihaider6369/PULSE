"""Automated tests for Live Monitor Shared Storage and Serverless Synchronization.

Verifies:
1. Upstash REST API command serialization and responses.
2. Standard Redis client backend handling.
3. In-memory local development fallback and TTL auto-expiration.
4. Production/Serverless enforcement: refusal of in-memory process state.
5. End-to-end multi-client shared state via FastAPI /api/live endpoints.
6. Graceful error handling (HTTP 503 on unconfigured, HTTP 502 on storage errors).
7. User-scoped isolation when authentication headers are present.
"""
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND_DIR))

from app.core.security import create_access_token
from app.core.config import settings
from app.main import app
from app.services import live_status
from app.services.live_status import (
    DEFAULT_STATE,
    InMemoryLiveStorage,
    LiveStorageConfigError,
    LiveStorageError,
    RedisClientLiveStorage,
    UnconfiguredLiveStorage,
    UpstashRestLiveStorage,
    get_storage_backend,
    reset_storage_backend,
    set_storage_backend,
)


@pytest.fixture(autouse=True)
def clean_storage_backend():
    """Ensure every test starts and ends with a clean storage state."""
    reset_storage_backend()
    yield
    reset_storage_backend()


# ---------------- Unit Tests for Storage Backends ----------------


def test_in_memory_storage_read_write_delete():
    """Verify InMemoryLiveStorage correctly sets, gets, and deletes data."""
    store = InMemoryLiveStorage()
    sample = {"active": True, "posture": "good", "warnings": 0}

    store.set("test_key", sample, ttl_seconds=10)
    read_back = store.get("test_key")
    assert read_back == sample
    assert read_back is not sample  # Must be a copy, not mutated reference

    store.delete("test_key")
    assert store.get("test_key") is None


def test_in_memory_storage_ttl_expiration():
    """Verify InMemoryLiveStorage purges keys after TTL expires."""
    store = InMemoryLiveStorage()
    store.set("quick_key", {"status": "ok"}, ttl_seconds=1)

    assert store.get("quick_key") == {"status": "ok"}
    time.sleep(1.1)
    assert store.get("quick_key") is None


def test_upstash_rest_storage_commands():
    """Verify UpstashRestLiveStorage executes HTTP REST commands with correct headers and payloads."""
    storage = UpstashRestLiveStorage(
        url="https://fake-upstash.upstash.io",
        token="test_token_xyz",
        timeout=1.0,
    )

    def make_mock_urlopen(result_dict):
        mock_ctx = MagicMock()
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(result_dict).encode("utf-8")
        mock_ctx.__enter__.return_value = mock_resp
        return mock_ctx

    # 1. Test SET command
    with patch("urllib.request.urlopen", return_value=make_mock_urlopen({"result": "OK"})) as mock_urlopen:
        storage.set("pulse:live:latest", {"active": True}, ttl_seconds=15)
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        assert req.get_header("Authorization") == "Bearer test_token_xyz"
        assert req.get_header("Content-type") == "application/json"
        cmd = json.loads(req.data.decode("utf-8"))
        assert cmd == ["SET", "pulse:live:latest", '{"active": true}', "EX", "15"]

    # 2. Test GET command
    with patch("urllib.request.urlopen", return_value=make_mock_urlopen({"result": '{"active": true, "posture": "good"}'})):
        res = storage.get("pulse:live:latest")
        assert res == {"active": True, "posture": "good"}

    # 3. Test GET missing/expired key
    with patch("urllib.request.urlopen", return_value=make_mock_urlopen({"result": None})):
        assert storage.get("nonexistent") is None

    # 4. Test Error response from Upstash
    with patch("urllib.request.urlopen", return_value=make_mock_urlopen({"error": "Unauthorized"})):
        with pytest.raises(LiveStorageError, match="Upstash error: Unauthorized"):
            storage.get("error_key")


def test_redis_client_storage():
    """Verify RedisClientLiveStorage interfaces with redis-py."""
    mock_redis = MagicMock()
    mock_client = MagicMock()
    mock_redis.from_url.return_value = mock_client

    with patch.dict("sys.modules", {"redis": mock_redis}):
        storage = RedisClientLiveStorage("rediss://fake-redis:6379")
        mock_redis.from_url.assert_called_once()

        # Set
        storage.set("test_key", {"active": True}, ttl_seconds=10)
        mock_client.set.assert_called_once_with("test_key", '{"active": true}', ex=10)

        # Get
        mock_client.get.return_value = '{"active": true}'
        assert storage.get("test_key") == {"active": True}

        # Delete
        storage.delete("test_key")
        mock_client.delete.assert_called_once_with("test_key")


def test_production_enforcement_blocks_in_memory():
    """Verify that in production mode, missing storage configuration raises LiveStorageConfigError."""
    with patch.object(settings, "environment", "production"):
        with patch.object(settings, "upstash_redis_rest_url", ""):
            with patch.object(settings, "redis_url", ""):
                with patch.dict("os.environ", {"UPSTASH_REDIS_REST_URL": "", "REDIS_URL": "", "KV_REST_API_URL": "", "KV_URL": ""}):
                    backend = get_storage_backend()
                    assert isinstance(backend, UnconfiguredLiveStorage)
                    with pytest.raises(LiveStorageConfigError, match="Shared live storage is not configured"):
                        backend.get("any_key")


def test_serverless_env_blocks_in_memory():
    """Verify that in Vercel serverless mode, missing storage configuration raises LiveStorageConfigError."""
    with patch.dict("os.environ", {"VERCEL": "1", "UPSTASH_REDIS_REST_URL": "", "REDIS_URL": "", "KV_REST_API_URL": ""}):
        with patch.object(settings, "upstash_redis_rest_url", ""):
            with patch.object(settings, "redis_url", ""):
                backend = get_storage_backend()
                assert isinstance(backend, UnconfiguredLiveStorage)
                with pytest.raises(LiveStorageConfigError):
                    backend.set("test", {"active": True}, 10)


# ---------------- API Integration Tests ----------------


def test_shared_state_write_and_read_across_clients():
    """Verify desktop client writes live state and web client reads the identical state."""
    shared_store = InMemoryLiveStorage()
    set_storage_backend(shared_store)

    client1 = TestClient(app)
    client2 = TestClient(app)

    # Initially off
    res_initial = client2.get("/api/live/status")
    assert res_initial.status_code == 200
    assert res_initial.json()["active"] is False

    # Client 1 (Desktop) writes live status
    post_payload = {
        "active": True,
        "session_id": 99,
        "posture": "good",
        "confidence": 0.95,
        "warnings": 3,
        "good_seconds": 120.0,
        "poor_seconds": 15.0,
    }
    res_write = client1.post("/api/live/status", json=post_payload)
    assert res_write.status_code == 200
    assert res_write.json()["active"] is True
    assert res_write.json()["posture"] == "good"

    # Client 2 (Website) reads the shared status
    res_read = client2.get("/api/live/status")
    assert res_read.status_code == 200
    data = res_read.json()
    assert data["active"] is True
    assert data["session_id"] == 99
    assert data["posture"] == "good"
    assert data["warnings"] == 3
    assert data["good_seconds"] == 120.0
    assert data["poor_seconds"] == 15.0
    assert data["updated_at"] is not None


def test_live_api_stop_session():
    """Verify posting stop marks state inactive for subsequent readers."""
    shared_store = InMemoryLiveStorage()
    set_storage_backend(shared_store)

    client = TestClient(app)

    client.post("/api/live/status", json={"active": True, "posture": "poor_posture"})
    assert client.get("/api/live/status").json()["active"] is True

    # Desktop stops monitor
    res_stop = client.post("/api/live/stop")
    assert res_stop.status_code == 200
    assert res_stop.json()["active"] is False
    assert res_stop.json()["posture"] is None

    # Web dashboard sees stopped monitor
    assert client.get("/api/live/status").json()["active"] is False


def test_live_api_unconfigured_storage_returns_503():
    """Verify that unconfigured storage returns HTTP 503 with helpful diagnostic error."""
    set_storage_backend(UnconfiguredLiveStorage())
    client = TestClient(app)

    # GET returns 503
    res_get = client.get("/api/live/status")
    assert res_get.status_code == 503
    assert "Shared live storage is not configured" in res_get.json()["detail"]

    # POST returns 503
    res_post = client.post("/api/live/status", json={"active": True})
    assert res_post.status_code == 503
    assert "Shared live storage is not configured" in res_post.json()["detail"]

    # STOP returns 503
    res_stop = client.post("/api/live/stop")
    assert res_stop.status_code == 503


def test_live_api_storage_error_returns_502():
    """Verify storage communication failure gracefully returns HTTP 502 rather than crashing."""
    faulty_storage = MagicMock()
    faulty_storage.get.side_effect = LiveStorageError("Connection timeout to Redis cluster")
    faulty_storage.set.side_effect = LiveStorageError("Connection timeout to Redis cluster")
    set_storage_backend(faulty_storage)

    client = TestClient(app)

    res_get = client.get("/api/live/status")
    assert res_get.status_code == 502
    assert "Live storage communication error" in res_get.json()["detail"]


def test_live_api_diagnostics_endpoint():
    """Verify /api/live/diagnostics returns configuration health details."""
    set_storage_backend(InMemoryLiveStorage())
    client = TestClient(app)

    res = client.get("/api/live/diagnostics")
    assert res.status_code == 200
    diag = res.json()
    assert diag["configured"] is True
    assert diag["storage_type"] == "in_memory_dev"
    assert "ttl_seconds" in diag


def test_user_scoped_live_state_isolation():
    """Verify that authenticated users store and retrieve their own isolated live status."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.database.session import Base, get_db

    shared_store = InMemoryLiveStorage()
    set_storage_backend(shared_store)

    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    db = TestingSession()

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        res_u1 = client.post("/api/auth/signup", json={"email": "live_u1@example.com", "password": "Password123!"})
        res_u2 = client.post("/api/auth/signup", json={"email": "live_u2@example.com", "password": "Password123!"})
        token_user_1 = res_u1.json()["access_token"]
        token_user_2 = res_u2.json()["access_token"]

        # User 1 posts live status
        client.post(
            "/api/live/status",
            json={"active": True, "session_id": 101, "posture": "good"},
            headers={"Authorization": f"Bearer {token_user_1}"},
        )

        # User 2 posts live status
        client.post(
            "/api/live/status",
            json={"active": True, "session_id": 202, "posture": "poor_posture"},
            headers={"Authorization": f"Bearer {token_user_2}"},
        )

        # User 1 retrieves User 1's status
        res1 = client.get("/api/live/status", headers={"Authorization": f"Bearer {token_user_1}"})
        assert res1.status_code == 200
        assert res1.json()["session_id"] == 101
        assert res1.json()["posture"] == "good"

        # User 2 retrieves User 2's status
        res2 = client.get("/api/live/status", headers={"Authorization": f"Bearer {token_user_2}"})
        assert res2.status_code == 200
        assert res2.json()["session_id"] == 202
        assert res2.json()["posture"] == "poor_posture"
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(bind=test_engine)
