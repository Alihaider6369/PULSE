"""Automated tests for Web Dashboard endpoints and multi-user data isolation."""
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

from app.database.session import Base, get_db
from app.main import app

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


def test_dashboard_user_session_visibility(client):
    """Verify that sessions synced by User A appear in User A's dashboard and NOT in User B's dashboard."""
    # 1. Register User A and User B
    res_a = client.post("/api/auth/signup", json={"email": "dash_a@example.com", "password": "Password123!"})
    token_a = res_a.json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    res_b = client.post("/api/auth/signup", json={"email": "dash_b@example.com", "password": "Password123!"})
    token_b = res_b.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 2. User A syncs 2 sessions
    now_iso = datetime.now(timezone.utc).isoformat()
    client.post("/api/sessions/sync", json={
        "sessions": [
            {
                "client_uuid": "dash-session-a1",
                "session_code": "codeA1",
                "started_at": now_iso,
                "ended_at": now_iso,
                "duration_seconds": 60.0,
                "good_seconds": 50.0,
                "poor_seconds": 10.0,
                "warning_count": 0,
                "awareness_score": 83.3,
                "events": [],
            },
            {
                "client_uuid": "dash-session-a2",
                "session_code": "codeA2",
                "started_at": now_iso,
                "ended_at": now_iso,
                "duration_seconds": 120.0,
                "good_seconds": 60.0,
                "poor_seconds": 60.0,
                "warning_count": 2,
                "awareness_score": 50.0,
                "events": [],
            },
        ]
    }, headers=headers_a)

    # 3. User A dashboard fetches /api/sessions -> sees 2 sessions
    res_dash_a = client.get("/api/sessions", headers=headers_a)
    assert res_dash_a.status_code == 200
    sessions_a = res_dash_a.json()
    assert len(sessions_a) == 2
    assert {s["client_uuid"] for s in sessions_a} == {"dash-session-a1", "dash-session-a2"}

    # 4. User B dashboard fetches /api/sessions -> sees 0 sessions
    res_dash_b = client.get("/api/sessions", headers=headers_b)
    assert res_dash_b.status_code == 200
    assert len(res_dash_b.json()) == 0


def test_dashboard_static_pages_availability(client):
    """Verify that frontend HTML assets and health endpoint respond with 200."""
    res_index = client.get("/")
    assert res_index.status_code == 200
    assert "PULSE" in res_index.text

    res_history = client.get("/history.html")
    assert res_history.status_code == 200

    res_settings = client.get("/settings.html")
    assert res_settings.status_code == 200

    res_live = client.get("/live.html")
    assert res_live.status_code == 200

    res_health = client.get("/api/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "ok"
