"""Durable, versioned SQLite local storage for offline sessions, events, and sync queues."""
import json
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from desktop_app.config import APP_DATA_DIR, OFFLINE_CACHE_FILE

LOCAL_DB_PATH = APP_DATA_DIR / "pulse_local.db"
CURRENT_SCHEMA_VERSION = 1


class LocalStorage:
    """Thread-safe SQLite storage manager for offline data and sync queue."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or LOCAL_DB_PATH
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA user_version;")
                version = cursor.fetchone()[0]

                if version == 0:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS local_sessions (
                            client_uuid TEXT PRIMARY KEY,
                            user_email TEXT,
                            session_code TEXT NOT NULL,
                            started_at TEXT NOT NULL,
                            ended_at TEXT,
                            duration_seconds REAL NOT NULL DEFAULT 0.0,
                            good_seconds REAL NOT NULL DEFAULT 0.0,
                            poor_seconds REAL NOT NULL DEFAULT 0.0,
                            warning_count INTEGER NOT NULL DEFAULT 0,
                            awareness_score REAL,
                            sync_status TEXT NOT NULL DEFAULT 'pending',
                            server_id INTEGER,
                            retry_count INTEGER NOT NULL DEFAULT 0,
                            next_retry_at REAL NOT NULL DEFAULT 0.0,
                            last_error TEXT,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        );
                    """)
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS ix_local_sessions_sync 
                        ON local_sessions(sync_status, next_retry_at);
                    """)
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS ix_local_sessions_user 
                        ON local_sessions(user_email);
                    """)
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS local_posture_events (
                            client_uuid TEXT PRIMARY KEY,
                            session_client_uuid TEXT NOT NULL,
                            occurred_at TEXT NOT NULL,
                            posture_class TEXT NOT NULL,
                            confidence REAL,
                            duration_seconds REAL NOT NULL DEFAULT 0.0,
                            is_warning INTEGER NOT NULL DEFAULT 0,
                            sync_status TEXT NOT NULL DEFAULT 'pending',
                            FOREIGN KEY(session_client_uuid) REFERENCES local_sessions(client_uuid) ON DELETE CASCADE
                        );
                    """)
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS sync_meta (
                            key TEXT PRIMARY KEY,
                            value TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        );
                    """)
                    cursor.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION};")
                    conn.commit()

    # ---------------- Legacy JSON Migration ----------------

    def migrate_legacy_json_cache(self, json_file: Optional[Path] = None) -> int:
        """Migrate existing records from offline_sessions.json into SQLite.
        
        Never deletes the JSON file; renames it to .migrated only after verifying record count.
        """
        target_file = json_file or OFFLINE_CACHE_FILE
        if not target_file.exists():
            return 0

        try:
            with open(target_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            print(f"Warning: Could not read legacy offline cache for migration: {exc}")
            return 0

        if not isinstance(data, list) or len(data) == 0:
            return 0

        migrated_count = 0
        now_iso = datetime.now(timezone.utc).isoformat()

        with self._lock:
            with self._get_connection() as conn:
                for item in data:
                    session_code = item.get("session_code") or uuid.uuid4().hex[:8]
                    # Deterministic UUID based on session_code and started_at to prevent duplicates on repeated runs
                    started_at = item.get("started_at") or now_iso
                    client_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{session_code}_{started_at}"))

                    cursor = conn.cursor()
                    cursor.execute("SELECT client_uuid FROM local_sessions WHERE client_uuid = ?", (client_uuid,))
                    if cursor.fetchone():
                        migrated_count += 1
                        continue

                    cursor.execute("""
                        INSERT INTO local_sessions (
                            client_uuid, user_email, session_code, started_at, ended_at,
                            duration_seconds, good_seconds, poor_seconds, warning_count,
                            awareness_score, sync_status, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """, (
                        client_uuid,
                        None,  # Legacy sessions belong to local unauthenticated profile
                        session_code,
                        started_at,
                        item.get("ended_at") or started_at,
                        float(item.get("duration_seconds") or 0.0),
                        float(item.get("good_seconds") or 0.0),
                        float(item.get("poor_seconds") or 0.0),
                        int(item.get("warning_count") or 0),
                        float(item["awareness_score"]) if item.get("awareness_score") is not None else None,
                        "pending",
                        now_iso,
                        now_iso,
                    ))
                    migrated_count += 1
                conn.commit()

        # Verify that record counts match before renaming JSON cache
        if migrated_count >= len(data):
            try:
                migrated_backup = target_file.with_name(target_file.name + ".migrated")
                target_file.replace(migrated_backup)
            except Exception as exc:
                print(f"Notice: Legacy JSON migrated successfully but could not rename file: {exc}")

        return migrated_count

    # ---------------- Session CRUD ----------------

    def create_session(
        self, session_code: str, user_email: Optional[str] = None, client_uuid: Optional[str] = None
    ) -> str:
        c_uuid = client_uuid or str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()

        with self._lock:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO local_sessions (
                        client_uuid, user_email, session_code, started_at,
                        sync_status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'pending', ?, ?);
                """, (c_uuid, user_email, session_code, now_iso, now_iso, now_iso))
                conn.commit()
        return c_uuid

    def end_session(
        self,
        client_uuid: str,
        good_seconds: float,
        poor_seconds: float,
        warning_count: int,
        server_id: Optional[int] = None,
        sync_status: str = "pending",
    ) -> Dict[str, Any]:
        total = good_seconds + poor_seconds
        score = round(good_seconds / total * 100, 1) if total > 0 else None
        now_iso = datetime.now(timezone.utc).isoformat()

        with self._lock:
            with self._get_connection() as conn:
                conn.execute("""
                    UPDATE local_sessions SET
                        ended_at = ?,
                        duration_seconds = ?,
                        good_seconds = ?,
                        poor_seconds = ?,
                        warning_count = ?,
                        awareness_score = ?,
                        server_id = COALESCE(?, server_id),
                        sync_status = ?,
                        updated_at = ?
                    WHERE client_uuid = ?;
                """, (
                    now_iso, total, good_seconds, poor_seconds,
                    warning_count, score, server_id, sync_status,
                    now_iso, client_uuid,
                ))
                conn.commit()

        return self.get_session(client_uuid) or {}

    def get_session(self, client_uuid: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT * FROM local_sessions WHERE client_uuid = ?", (client_uuid,)
                ).fetchone()
                return dict(row) if row else None

    def add_posture_event(
        self,
        session_client_uuid: str,
        posture_class: str,
        duration_seconds: float,
        is_warning: bool = True,
        confidence: Optional[float] = None,
        event_uuid: Optional[str] = None,
    ) -> str:
        e_uuid = event_uuid or str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()

        with self._lock:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO local_posture_events (
                        client_uuid, session_client_uuid, occurred_at,
                        posture_class, confidence, duration_seconds,
                        is_warning, sync_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending');
                """, (
                    e_uuid, session_client_uuid, now_iso,
                    posture_class, confidence, duration_seconds,
                    1 if is_warning else 0,
                ))
                conn.commit()
        return e_uuid

    def get_session_events(self, session_client_uuid: str) -> List[Dict[str, Any]]:
        with self._lock:
            with self._get_connection() as conn:
                rows = conn.execute(
                    "SELECT * FROM local_posture_events WHERE session_client_uuid = ? ORDER BY occurred_at ASC",
                    (session_client_uuid,),
                ).fetchall()
                return [dict(r) for r in rows]

    # ---------------- Sync Queue & Retry Logic ----------------

    def get_pending_sync_sessions(
        self, user_email: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Return sessions ready for sync (pending or failed whose backoff delay has passed)."""
        now_ts = time.time()
        with self._lock:
            with self._get_connection() as conn:
                query = """
                    SELECT * FROM local_sessions
                    WHERE sync_status IN ('pending', 'failed')
                      AND next_retry_at <= ?
                """
                params: List[Any] = [now_ts]
                if user_email:
                    # Sync only sessions belonging to current user or unassigned legacy sessions
                    query += " AND (user_email = ? OR user_email IS NULL)"
                    params.append(user_email)

                query += " ORDER BY started_at ASC LIMIT ?"
                params.append(limit)

                rows = conn.execute(query, params).fetchall()
                result = []
                for row in rows:
                    item = dict(row)
                    # Include child events
                    event_rows = conn.execute(
                        "SELECT * FROM local_posture_events WHERE session_client_uuid = ?",
                        (item["client_uuid"],),
                    ).fetchall()
                    item["events"] = [dict(e) for e in event_rows]
                    result.append(item)
                return result

    def mark_session_syncing(self, client_uuid: str) -> None:
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    "UPDATE local_sessions SET sync_status = 'syncing' WHERE client_uuid = ?",
                    (client_uuid,),
                )
                conn.commit()

    def mark_session_synced(self, client_uuid: str, server_id: Optional[int] = None) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("""
                    UPDATE local_sessions SET
                        sync_status = 'synced',
                        server_id = COALESCE(?, server_id),
                        last_error = NULL,
                        updated_at = ?
                    WHERE client_uuid = ?;
                """, (server_id, now_iso, client_uuid))
                conn.execute(
                    "UPDATE local_posture_events SET sync_status = 'synced' WHERE session_client_uuid = ?",
                    (client_uuid,),
                )
                conn.commit()

    def mark_session_failed(
        self,
        client_uuid: str,
        error_msg: str,
        base_backoff: float = 2.0,
        max_backoff: float = 300.0,
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        now_ts = time.time()
        with self._lock:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT retry_count FROM local_sessions WHERE client_uuid = ?", (client_uuid,)
                ).fetchone()
                retries = (row["retry_count"] if row else 0) + 1
                # Bounded exponential backoff: delay = min(max_backoff, base * 2^retries)
                delay = min(max_backoff, base_backoff * (2 ** min(retries, 8)))
                next_retry = now_ts + delay

                conn.execute("""
                    UPDATE local_sessions SET
                        sync_status = 'failed',
                        retry_count = ?,
                        next_retry_at = ?,
                        last_error = ?,
                        updated_at = ?
                    WHERE client_uuid = ?;
                """, (retries, next_retry, error_msg[:500], now_iso, client_uuid))
                conn.commit()

    def get_sync_stats(self, user_email: Optional[str] = None) -> Dict[str, int]:
        with self._lock:
            with self._get_connection() as conn:
                where = ""
                params: List[Any] = []
                if user_email:
                    where = "WHERE user_email = ? OR user_email IS NULL"
                    params.append(user_email)

                rows = conn.execute(
                    f"SELECT sync_status, COUNT(*) as cnt FROM local_sessions {where} GROUP BY sync_status",
                    params,
                ).fetchall()
                stats = {"pending": 0, "syncing": 0, "synced": 0, "failed": 0, "total": 0}
                for r in rows:
                    st = r["sync_status"]
                    cnt = r["cnt"]
                    if st in stats:
                        stats[st] = cnt
                    stats["total"] += cnt
                return stats

    def list_all_sessions(self, user_email: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return all local sessions ordered by started_at desc."""
        with self._lock:
            with self._get_connection() as conn:
                where = ""
                params: List[Any] = []
                if user_email:
                    where = "WHERE user_email = ? OR user_email IS NULL"
                    params.append(user_email)

                rows = conn.execute(
                    f"SELECT * FROM local_sessions {where} ORDER BY started_at DESC", params
                ).fetchall()
                return [dict(r) for r in rows]

    # ---------------- Metadata Store ----------------

    def set_meta(self, key: str, value: str) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO sync_meta (key, value, updated_at) VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at;
                """, (key, value, now_iso))
                conn.commit()

    def get_meta(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self._lock:
            with self._get_connection() as conn:
                row = conn.execute("SELECT value FROM sync_meta WHERE key = ?", (key,)).fetchone()
                return row["value"] if row else default
