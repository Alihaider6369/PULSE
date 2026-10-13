"""Automated test suite for SQLite persistence, legacy migration, and offline retry logic."""
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from desktop_app.core.storage import LocalStorage


def test_sqlite_persistence_and_events(tmp_path):
    """Verify that sessions and events survive restarts and database reconnects."""
    db_file = tmp_path / "test_persistence.db"

    # Step 1: Create session and events
    storage1 = LocalStorage(db_path=db_file)
    session_uuid = storage1.create_session(session_code="sess_persist_01", user_email="tester@example.com")
    event1 = storage1.add_posture_event(
        session_client_uuid=session_uuid,
        posture_class="poor_posture",
        duration_seconds=30.0,
        is_warning=True,
    )
    storage1.end_session(
        client_uuid=session_uuid,
        good_seconds=60.0,
        poor_seconds=40.0,
        warning_count=1,
    )

    # Step 2: Simulate application restart by reopening the database file
    storage2 = LocalStorage(db_path=db_file)
    restored = storage2.get_session(session_uuid)

    assert restored is not None
    assert restored["session_code"] == "sess_persist_01"
    assert restored["user_email"] == "tester@example.com"
    assert restored["good_seconds"] == 60.0
    assert restored["poor_seconds"] == 40.0
    assert restored["awareness_score"] == 60.0
    assert restored["sync_status"] == "pending"

    # Verify event was persisted
    events = storage2.get_session_events(session_uuid)
    assert len(events) == 1
    assert events[0]["client_uuid"] == event1
    assert events[0]["posture_class"] == "poor_posture"


def test_migration_from_legacy_json(tmp_path):
    """Verify safe migration of legacy offline JSON records to SQLite and backup preservation."""
    json_file = tmp_path / "offline_sessions.json"
    dummy_records = [
        {
            "id": "local_abc1",
            "session_code": "abc1",
            "started_at": "2026-10-10T12:00:00+00:00",
            "ended_at": "2026-10-10T12:10:00+00:00",
            "duration_seconds": 600.0,
            "good_seconds": 450.0,
            "poor_seconds": 150.0,
            "warning_count": 2,
            "awareness_score": 75.0,
            "is_offline": True,
        },
        {
            "id": "local_abc2",
            "session_code": "abc2",
            "started_at": "2026-10-10T14:00:00+00:00",
            "ended_at": "2026-10-10T14:05:00+00:00",
            "duration_seconds": 300.0,
            "good_seconds": 270.0,
            "poor_seconds": 30.0,
            "warning_count": 0,
            "awareness_score": 90.0,
            "is_offline": True,
        },
    ]

    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(dummy_records, f)

    db_file = tmp_path / "test_migration.db"
    storage = LocalStorage(db_path=db_file)

    migrated = storage.migrate_legacy_json_cache(json_file=json_file)
    assert migrated == 2

    # Verify SQLite records
    sessions = storage.list_all_sessions()
    assert len(sessions) == 2
    assert any(s["session_code"] == "abc1" for s in sessions)
    assert any(s["session_code"] == "abc2" for s in sessions)

    # Verify original file was renamed to .migrated (not deleted)
    assert json_file.exists() is False
    migrated_backup = json_file.with_name("offline_sessions.json.migrated")
    assert migrated_backup.exists() is True


def test_exponential_backoff_and_retry(tmp_path):
    """Verify that failed syncs apply bounded exponential backoff without losing records."""
    db_file = tmp_path / "test_backoff.db"
    storage = LocalStorage(db_path=db_file)

    session_uuid = storage.create_session(session_code="fail_sess_01")
    storage.end_session(session_uuid, 30.0, 10.0, 0)

    # 1. Initial state: ready for sync
    pending = storage.get_pending_sync_sessions()
    assert len(pending) == 1

    # 2. First failure: retry_count=1 -> backoff delay = min(300, 2 * 2^1) = 4s
    t_before = time.time()
    storage.mark_session_failed(session_uuid, error_msg="Network timeout", base_backoff=2.0)
    sess = storage.get_session(session_uuid)
    assert sess["sync_status"] == "failed"
    assert sess["retry_count"] == 1
    assert sess["next_retry_at"] >= t_before + 3.9

    # Now, queue should NOT return this session immediately because next_retry_at is in the future
    assert len(storage.get_pending_sync_sessions()) == 0

    # 3. Simulate second failure: retry_count=2 -> delay = 2 * 2^2 = 8s
    storage.mark_session_failed(session_uuid, error_msg="Server unavailable", base_backoff=2.0)
    sess2 = storage.get_session(session_uuid)
    assert sess2["retry_count"] == 2
    assert sess2["last_error"] == "Server unavailable"

    # 4. Successful sync
    storage.mark_session_synced(session_uuid, server_id=99)
    sess_synced = storage.get_session(session_uuid)
    assert sess_synced["sync_status"] == "synced"
    assert sess_synced["server_id"] == 99
    assert sess_synced["last_error"] is None
