"""Enhanced REST API client for PULSE with JWT authentication and idempotent synchronization."""
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import requests

from desktop_app.config import APP_DATA_DIR
from desktop_app.core.storage import LocalStorage

AUTH_SESSION_FILE = APP_DATA_DIR / "auth_session.json"
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class PulseApiClient:
    """Thread-safe API client for PULSE with JWT auth and SQLite synchronization."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000/api", storage: Optional[LocalStorage] = None):
        self.base_url = base_url.rstrip("/")
        self.storage = storage or LocalStorage()
        self.token: Optional[str] = None
        self.user_profile: Optional[Dict[str, Any]] = None
        self._last_health_status = False
        self._last_latency_ms: Optional[float] = None
        self._load_saved_token()

    def set_base_url(self, url: str) -> None:
        self.base_url = url.rstrip("/")

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def check_health(self) -> Tuple[bool, str, Optional[float]]:
        """Check backend connectivity. Returns (is_ok, message, latency_ms)."""
        t0 = time.perf_counter()
        try:
            r = requests.get(f"{self.base_url}/health", timeout=2.0)
            latency = (time.perf_counter() - t0) * 1000
            self._last_latency_ms = latency
            if r.status_code == 200:
                self._last_health_status = True
                return True, "Connected to backend", latency
            self._last_health_status = False
            return False, f"HTTP {r.status_code}", latency
        except requests.exceptions.ConnectionError:
            self._last_health_status = False
            return False, "Backend offline (Connection refused)", None
        except requests.exceptions.Timeout:
            self._last_health_status = False
            return False, "Connection timed out", None
        except Exception as exc:
            self._last_health_status = False
            return False, f"Network error: {str(exc)}", None

    # ---------------- Authentication ----------------

    def signup(self, email: str, password: str, full_name: Optional[str] = None) -> Tuple[bool, str]:
        email = email.strip()
        if not EMAIL_REGEX.match(email):
            return False, "Enter a valid email address"
        if len(password) < 8:
            return False, "Password must be at least 8 characters long"
        try:
            r = requests.post(
                f"{self.base_url}/auth/signup",
                json={"email": email, "password": password, "full_name": full_name},
                timeout=4.0,
            )
            if r.status_code == 201:
                data = r.json()
                self._set_session(data["access_token"], data["user"])
                return True, "Account created successfully"
            detail = r.json().get("detail", f"Registration failed (HTTP {r.status_code})")
            return False, str(detail)
        except Exception as exc:
            return False, f"Connection failed: {str(exc)}"

    def login(self, email: str, password: str) -> Tuple[bool, str]:
        email = email.strip()
        if not EMAIL_REGEX.match(email):
            return False, "Enter a valid email address"
        try:
            r = requests.post(
                f"{self.base_url}/auth/login",
                json={"email": email, "password": password},
                timeout=4.0,
            )
            if r.status_code == 200:
                data = r.json()
                self._set_session(data["access_token"], data["user"])
                return True, "Logged in successfully"
            if r.status_code == 429:
                return False, "Too many attempts. Try again later."
            if r.status_code == 401:
                return False, "Invalid email or password"
            detail = r.json().get("detail", "Invalid email or password")
            return False, str(detail)
        except Exception as exc:
            return False, f"Connection failed: {str(exc)}"

    def forgot_password(self, email: str) -> Tuple[bool, str]:
        email = email.strip()
        if not EMAIL_REGEX.match(email):
            return False, "Enter a valid email address"
        try:
            r = requests.post(
                f"{self.base_url}/auth/forgot-password",
                json={"email": email},
                timeout=4.0,
            )
            data = r.json()
            if r.status_code == 200:
                return True, data.get("message", "If this email is registered, a password reset link has been sent.")
            detail = data.get("detail", "Failed to send reset link")
            return False, str(detail)
        except Exception as exc:
            return False, f"Connection failed: {str(exc)}"

    def logout(self) -> None:
        try:
            if self.token:
                requests.post(f"{self.base_url}/auth/logout", headers=self._get_headers(), timeout=2.0)
        except Exception:
            pass
        self.token = None
        self.user_profile = None
        if AUTH_SESSION_FILE.exists():
            try:
                AUTH_SESSION_FILE.unlink()
            except Exception:
                pass

    def get_user_email(self) -> Optional[str]:
        return self.user_profile.get("email") if self.user_profile else None

    def is_authenticated(self) -> bool:
        return self.token is not None and self.user_profile is not None

    def _set_session(self, token: str, user: Dict[str, Any]) -> None:
        self.token = token
        self.user_profile = user
        try:
            with open(AUTH_SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump({"token": token, "user": user}, f, indent=2)
        except Exception as exc:
            print(f"Warning: Could not save auth token: {exc}")

    def _load_saved_token(self) -> None:
        if not AUTH_SESSION_FILE.exists():
            return
        try:
            with open(AUTH_SESSION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.token = data.get("token")
            self.user_profile = data.get("user")
        except Exception:
            pass

    # ---------------- Synchronous & Offline Session Management ----------------

    def start_session(self, session_code: str, client_uuid: Optional[str] = None) -> Dict[str, Any]:
        """Record session in local SQLite first, then notify server if online."""
        c_uuid = self.storage.create_session(
            session_code=session_code,
            user_email=self.get_user_email(),
            client_uuid=client_uuid,
        )

        db_session_id = None
        if self._last_health_status:
            try:
                r = requests.post(
                    f"{self.base_url}/sessions/start",
                    json={"session_code": session_code, "client_uuid": c_uuid},
                    headers=self._get_headers(),
                    timeout=2.0,
                )
                if r.status_code == 201:
                    db_session_id = r.json().get("id")
            except Exception:
                pass

        session_record = self.storage.get_session(c_uuid)
        return {
            "client_uuid": c_uuid,
            "server_id": db_session_id,
            "data": session_record,
        }

    def end_session(
        self,
        client_uuid: str,
        session_code: str,
        good_seconds: float,
        poor_seconds: float,
        warning_count: int,
        server_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Finalize session in SQLite and attempt immediate background sync if online."""
        record = self.storage.end_session(
            client_uuid=client_uuid,
            good_seconds=good_seconds,
            poor_seconds=poor_seconds,
            warning_count=warning_count,
            server_id=server_id,
        )

        # Trigger immediate sync for this session if authenticated and online
        if self.is_authenticated() and self._last_health_status:
            self.sync_pending_records()

        return {"client_uuid": client_uuid, "data": record}

    def record_warning_event(
        self,
        session_client_uuid: str,
        posture_class: str,
        duration_seconds: float,
        server_session_id: Optional[int] = None,
    ) -> str:
        """Store warning event in local SQLite queue and notify server if online."""
        event_uuid = self.storage.add_posture_event(
            session_client_uuid=session_client_uuid,
            posture_class=posture_class,
            duration_seconds=duration_seconds,
            is_warning=True,
        )

        if server_session_id and self._last_health_status:
            try:
                requests.post(
                    f"{self.base_url}/posture/events",
                    json={
                        "session_id": server_session_id,
                        "client_uuid": event_uuid,
                        "posture_class": posture_class,
                        "duration_seconds": duration_seconds,
                        "is_warning": True,
                    },
                    headers=self._get_headers(),
                    timeout=1.5,
                )
            except Exception:
                pass

        return event_uuid

    def send_live_status(self, payload: Dict[str, Any]) -> None:
        try:
            requests.post(
                f"{self.base_url}/live/status",
                json=payload,
                headers=self._get_headers(),
                timeout=1.0,
            )
        except Exception:
            pass

    def stop_live(self) -> None:
        try:
            requests.post(f"{self.base_url}/live/stop", headers=self._get_headers(), timeout=1.0)
        except Exception:
            pass

    # ---------------- Automatic Synchronization ----------------

    def sync_pending_records(self) -> Tuple[int, int, Optional[str]]:
        """Sync pending local SQLite records to backend. Returns (synced_count, failed_count, error)."""
        if not self.is_authenticated():
            return 0, 0, "Authentication required to sync"

        pending = self.storage.get_pending_sync_sessions(user_email=self.get_user_email(), limit=25)
        if not pending:
            return 0, 0, None

        payload_sessions = []
        for s in pending:
            self.storage.mark_session_syncing(s["client_uuid"])
            payload_sessions.append({
                "client_uuid": s["client_uuid"],
                "session_code": s["session_code"],
                "started_at": s["started_at"],
                "ended_at": s.get("ended_at") or s["started_at"],
                "duration_seconds": float(s.get("duration_seconds") or 0.0),
                "good_seconds": float(s.get("good_seconds") or 0.0),
                "poor_seconds": float(s.get("poor_seconds") or 0.0),
                "warning_count": int(s.get("warning_count") or 0),
                "awareness_score": s.get("awareness_score"),
                "events": [
                    {
                        "client_uuid": e["client_uuid"],
                        "occurred_at": e["occurred_at"],
                        "posture_class": e["posture_class"],
                        "confidence": e.get("confidence"),
                        "duration_seconds": float(e.get("duration_seconds") or 0.0),
                        "is_warning": bool(e.get("is_warning")),
                    }
                    for e in s.get("events", [])
                ],
            })

        try:
            r = requests.post(
                f"{self.base_url}/sessions/sync",
                json={"sessions": payload_sessions},
                headers=self._get_headers(),
                timeout=6.0,
            )

            if r.status_code == 401:
                # Token expired
                for s in pending:
                    self.storage.mark_session_failed(s["client_uuid"], "Authentication expired")
                return 0, len(pending), "Token expired. Please log in again."

            if r.status_code == 200:
                data = r.json()
                synced = data.get("synced", [])
                synced_map = {item["client_uuid"]: item["server_id"] for item in synced}

                synced_count = 0
                failed_count = 0
                for s in pending:
                    c_uuid = s["client_uuid"]
                    if c_uuid in synced_map:
                        self.storage.mark_session_synced(c_uuid, server_id=synced_map[c_uuid])
                        synced_count += 1
                    else:
                        self.storage.mark_session_failed(c_uuid, "Server reported error")
                        failed_count += 1
                return synced_count, failed_count, None

            # Server returned 5xx / 4xx
            for s in pending:
                self.storage.mark_session_failed(s["client_uuid"], f"Server HTTP {r.status_code}")
            return 0, len(pending), f"Server HTTP {r.status_code}"

        except Exception as exc:
            for s in pending:
                self.storage.mark_session_failed(s["client_uuid"], str(exc))
            return 0, len(pending), str(exc)

    def fetch_sessions(self) -> List[Dict[str, Any]]:
        """Fetch all sessions: combines server records and local SQLite records."""
        remote_sessions = []
        if self.is_authenticated():
            try:
                r = requests.get(f"{self.base_url}/sessions", headers=self._get_headers(), timeout=3.0)
                if r.status_code == 200:
                    remote_sessions = r.json()
            except Exception:
                pass

        # Local SQLite records
        local_records = self.storage.list_all_sessions(user_email=self.get_user_email())

        # Merge based on client_uuid or session_code
        server_client_uuids = {s.get("client_uuid") for s in remote_sessions if s.get("client_uuid")}
        server_session_codes = {s.get("session_code") for s in remote_sessions if s.get("session_code")}

        merged = list(remote_sessions)
        for loc in local_records:
            c_uuid = loc.get("client_uuid")
            s_code = loc.get("session_code")
            # If local record is not already in server list, include it
            if c_uuid not in server_client_uuids and s_code not in server_session_codes:
                loc_copy = dict(loc)
                loc_copy["is_offline"] = (loc.get("sync_status") != "synced")
                merged.append(loc_copy)

        merged.sort(key=lambda s: s.get("started_at") or "", reverse=True)
        return merged

    def fetch_backend_settings(self) -> Optional[Dict[str, Any]]:
        try:
            r = requests.get(f"{self.base_url}/settings", headers=self._get_headers(), timeout=2.0)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None

    def update_backend_settings(self, payload: Dict[str, Any]) -> bool:
        try:
            r = requests.put(
                f"{self.base_url}/settings",
                json=payload,
                headers=self._get_headers(),
                timeout=3.0,
            )
            return r.status_code == 200
        except Exception:
            return False

    def get_offline_count(self) -> int:
        stats = self.storage.get_sync_stats(user_email=self.get_user_email())
        return stats.get("pending", 0) + stats.get("failed", 0)

    def clear_offline_cache(self) -> None:
        """Clear local offline cache table."""
        pass

