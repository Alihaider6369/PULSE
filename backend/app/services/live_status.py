"""Live Monitor Shared State Service.

Supports multi-instance and serverless deployment (Vercel) via:
1. Upstash Redis REST API (stateless HTTPS, zero socket exhaustion)
2. Standard Redis protocol (TCP/TLS via REDIS_URL)
3. Local development in-memory fallback (strictly blocked in production/serverless)
"""
import copy
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.database.session import is_serverless_env

logger = logging.getLogger("pulse.live_status")

DEFAULT_STATE: Dict[str, Any] = {
    "active": False,
    "session_id": None,
    "posture": None,
    "confidence": None,
    "warnings": 0,
    "good_seconds": 0.0,
    "poor_seconds": 0.0,
    "updated_at": None,
}

LATEST_KEY = "pulse:live:latest"


class LiveStorageError(Exception):
    """Raised when shared live storage encounters a communication or operational error."""


class LiveStorageConfigError(LiveStorageError):
    """Raised when shared storage is required (e.g. production/serverless) but unconfigured."""


class BaseLiveStorage(ABC):
    """Abstract storage backend for live telemetry state."""

    storage_type: str = "base"

    @abstractmethod
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve state dictionary by key, or None if missing or expired."""

    @abstractmethod
    def set(self, key: str, data: Dict[str, Any], ttl_seconds: int) -> None:
        """Store state dictionary with expiration TTL in seconds."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete key from storage."""

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if storage backend is reachable and responsive."""


class UpstashRestLiveStorage(BaseLiveStorage):
    """Stateless HTTPS client for Upstash Redis REST API.

    Ideal for Vercel serverless functions: zero persistent TCP sockets,
    immune to connection pool exhaustion, and fast execution over HTTPS.
    """

    storage_type = "upstash_rest"

    def __init__(self, url: str, token: str, timeout: float = 3.0):
        self.url = url.rstrip("/")
        self.token = token.strip()
        self.timeout = timeout

    def _execute(self, command: List[Any]) -> Any:
        req = urllib.request.Request(
            self.url,
            data=json.dumps(command).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                payload = json.loads(raw)
                if isinstance(payload, dict) and "error" in payload:
                    raise LiveStorageError(f"Upstash error: {payload['error']}")
                return payload.get("result") if isinstance(payload, dict) else payload
        except urllib.error.HTTPError as exc:
            raise LiveStorageError(f"Upstash HTTP {exc.code}: {exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise LiveStorageError(f"Upstash connection failed: {exc.reason}") from exc
        except LiveStorageError:
            raise
        except Exception as exc:
            raise LiveStorageError(f"Upstash request failed: {exc}") from exc

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        res = self._execute(["GET", key])
        if res is None:
            return None
        if isinstance(res, str):
            try:
                return json.loads(res)
            except Exception:
                return None
        if isinstance(res, dict):
            return res
        return None

    def set(self, key: str, data: Dict[str, Any], ttl_seconds: int) -> None:
        payload = json.dumps(data)
        ttl = max(1, int(ttl_seconds))
        self._execute(["SET", key, payload, "EX", str(ttl)])

    def delete(self, key: str) -> None:
        self._execute(["DEL", key])

    def health_check(self) -> bool:
        try:
            res = self._execute(["PING"])
            return res == "PONG" or res == "OK"
        except Exception:
            return False


class RedisClientLiveStorage(BaseLiveStorage):
    """Standard Redis client using redis-py for TCP/TLS connections."""

    storage_type = "redis_client"

    def __init__(self, redis_url: str, timeout: float = 2.0):
        self.redis_url = redis_url
        self.timeout = timeout
        try:
            import redis
            self._redis_mod = redis
            self._client = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_timeout=timeout,
                socket_connect_timeout=timeout,
            )
        except ImportError as exc:
            raise LiveStorageError("redis package is required for REDIS_URL support. Install redis.") from exc

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        try:
            val = self._client.get(key)
            if val is None:
                return None
            return json.loads(val)
        except self._redis_mod.RedisError as exc:
            raise LiveStorageError(f"Redis get failed: {exc}") from exc
        except Exception as exc:
            raise LiveStorageError(f"Redis get error: {exc}") from exc

    def set(self, key: str, data: Dict[str, Any], ttl_seconds: int) -> None:
        try:
            val = json.dumps(data)
            ttl = max(1, int(ttl_seconds))
            self._client.set(key, val, ex=ttl)
        except self._redis_mod.RedisError as exc:
            raise LiveStorageError(f"Redis set failed: {exc}") from exc
        except Exception as exc:
            raise LiveStorageError(f"Redis set error: {exc}") from exc

    def delete(self, key: str) -> None:
        try:
            self._client.delete(key)
        except self._redis_mod.RedisError as exc:
            raise LiveStorageError(f"Redis delete failed: {exc}") from exc

    def health_check(self) -> bool:
        try:
            return bool(self._client.ping())
        except Exception:
            return False


class InMemoryLiveStorage(BaseLiveStorage):
    """Thread-safe in-memory storage with TTL support.

    Restricted strictly to local development and automated testing.
    Never used as production source of truth.
    """

    storage_type = "in_memory_dev"

    def __init__(self):
        self._lock = threading.Lock()
        self._store: Dict[str, tuple] = {}

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            if key not in self._store:
                return None
            data, expire_at = self._store[key]
            if expire_at is not None and time.time() > expire_at:
                del self._store[key]
                return None
            return copy.deepcopy(data)

    def set(self, key: str, data: Dict[str, Any], ttl_seconds: int) -> None:
        with self._lock:
            expire_at = (time.time() + ttl_seconds) if ttl_seconds > 0 else None
            self._store[key] = (copy.deepcopy(data), expire_at)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def health_check(self) -> bool:
        return True

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


class UnconfiguredLiveStorage(BaseLiveStorage):
    """Null storage backend that raises explicit diagnostic errors when storage is unconfigured."""

    storage_type = "unconfigured"

    def __init__(self, message: Optional[str] = None):
        self.message = message or (
            "Shared live storage is not configured. For Vercel serverless deployment, "
            "set UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN, or REDIS_URL in environment variables."
        )

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        raise LiveStorageConfigError(self.message)

    def set(self, key: str, data: Dict[str, Any], ttl_seconds: int) -> None:
        raise LiveStorageConfigError(self.message)

    def delete(self, key: str) -> None:
        raise LiveStorageConfigError(self.message)

    def health_check(self) -> bool:
        return False


_storage_override: Optional[BaseLiveStorage] = None
_in_memory_singleton: Optional[InMemoryLiveStorage] = None


def set_storage_backend(storage: Optional[BaseLiveStorage]) -> None:
    """Set an explicit storage backend (used for tests or custom injection)."""
    global _storage_override
    _storage_override = storage


def reset_storage_backend() -> None:
    """Clear any storage override."""
    global _storage_override
    _storage_override = None


def get_storage_backend() -> BaseLiveStorage:
    """Resolve the active live storage backend based on environment configuration."""
    if _storage_override is not None:
        return _storage_override

    upstash_url = settings.effective_upstash_url
    upstash_token = settings.effective_upstash_token
    if upstash_url and upstash_token:
        return UpstashRestLiveStorage(upstash_url, upstash_token)

    redis_url = settings.effective_redis_url
    if redis_url:
        return RedisClientLiveStorage(redis_url)

    # In serverless or production, fail explicitly rather than pretending in-memory works
    if is_serverless_env() or settings.environment == "production":
        return UnconfiguredLiveStorage()

    # Local development fallback
    global _in_memory_singleton
    if _in_memory_singleton is None:
        logger.warning(
            "Shared live storage not configured. Using in-memory fallback for local development. "
            "For serverless/production synchronization, configure UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN."
        )
        _in_memory_singleton = InMemoryLiveStorage()
    return _in_memory_singleton


def _key_for_user(user_id: Optional[int]) -> str:
    return f"pulse:live:user:{user_id}" if user_id is not None else "pulse:live:global"


def update(data: dict, user_id: Optional[int] = None) -> dict:
    """Merge latest monitor values into shared storage with TTL."""
    storage = get_storage_backend()
    ttl = max(1, settings.live_status_ttl_seconds)

    primary_key = _key_for_user(user_id)
    try:
        existing = storage.get(primary_key) or {}
    except LiveStorageConfigError:
        raise
    except Exception as exc:
        logger.warning(f"Failed to read existing live state for merge: {exc}")
        existing = {}

    merged = dict(DEFAULT_STATE)
    merged.update({k: v for k, v in existing.items() if k in merged})
    merged.update({k: v for k, v in data.items() if k in merged})
    merged["active"] = True
    merged["updated_at"] = datetime.now(timezone.utc).isoformat()

    storage.set(primary_key, merged, ttl_seconds=ttl)
    if primary_key != LATEST_KEY:
        storage.set(LATEST_KEY, merged, ttl_seconds=ttl)

    return dict(merged)


def get(user_id: Optional[int] = None) -> dict:
    """Retrieve live monitor state from shared storage. Returns DEFAULT_STATE if missing or expired."""
    storage = get_storage_backend()
    if user_id is not None:
        state = storage.get(f"pulse:live:user:{user_id}")
        if state is not None:
            return state

    state = storage.get(LATEST_KEY)
    if state is not None:
        return state

    return dict(DEFAULT_STATE)


def stop(user_id: Optional[int] = None) -> dict:
    """Mark monitor as stopped in shared storage."""
    storage = get_storage_backend()
    stopped = dict(DEFAULT_STATE)
    stopped["active"] = False
    stopped["posture"] = None
    stopped["updated_at"] = datetime.now(timezone.utc).isoformat()

    primary_key = _key_for_user(user_id)
    stop_ttl = min(10, max(1, settings.live_status_ttl_seconds))

    storage.set(primary_key, stopped, ttl_seconds=stop_ttl)
    if primary_key != LATEST_KEY:
        storage.set(LATEST_KEY, stopped, ttl_seconds=stop_ttl)

    return dict(stopped)


def get_storage_diagnostic() -> dict:
    """Return diagnostic details regarding the current shared storage configuration."""
    storage = get_storage_backend()
    is_serverless = is_serverless_env()
    is_configured = not isinstance(storage, UnconfiguredLiveStorage)
    return {
        "storage_type": getattr(storage, "storage_type", "unknown"),
        "configured": is_configured,
        "environment": settings.environment,
        "is_serverless": is_serverless,
        "ttl_seconds": settings.live_status_ttl_seconds,
        "status": "ready" if is_configured else "storage_required",
        "message": (
            "Shared live storage is operational."
            if is_configured
            else "Shared live storage is unconfigured. For Vercel serverless deployment, configure UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN, or REDIS_URL."
        ),
    }