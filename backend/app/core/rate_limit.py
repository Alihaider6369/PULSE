"""Rate limiter for authentication endpoints using database-backed counters and in-memory fallbacks."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import logging
import threading
from typing import Dict, List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from fastapi import Request

from app.models.rate_limit import RateLimitEvent

logger = logging.getLogger("pulse.rate_limit")
logger.setLevel(logging.INFO)


def ensure_rate_limit_table(db: Optional[DBSession] = None) -> None:
    """Harmless no-op: rate_limit_events table is created and managed by Alembic migrations."""
    pass


def get_client_ip(request: Request) -> str:
    """Extract client IP behind reverse proxies (Vercel) with safe fallbacks.

    Prioritizes X-Forwarded-For (first address), then X-Real-IP,
    falling back to request.client.host or '127.0.0.1'.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and forwarded.strip():
        first_ip = forwarded.split(",")[0].strip()
        if first_ip:
            return first_ip

    real_ip = request.headers.get("x-real-ip")
    if real_ip and real_ip.strip():
        return real_ip.strip()

    if request.client and request.client.host:
        return request.client.host.strip()

    return "127.0.0.1"


def cleanup_old_rate_limits(db: DBSession, window_seconds: int = 3600, key: Optional[str] = None) -> int:
    """Delete rate limit rows older than the window to prevent table bloat."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=window_seconds)
    query = db.query(RateLimitEvent).filter(RateLimitEvent.created_at < cutoff)
    if key:
        query = query.filter(RateLimitEvent.key == key)
    deleted = query.delete(synchronize_session=False)
    return deleted


def is_db_rate_limited(db: DBSession, key: str, max_attempts: int, window_seconds: int) -> bool:
    """Check if key has reached or exceeded max_attempts within the sliding window using database counters."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=window_seconds)
    count = db.query(func.count(RateLimitEvent.id)).filter(
        RateLimitEvent.key == key,
        RateLimitEvent.created_at >= cutoff,
    ).scalar() or 0
    return count >= max_attempts


def record_db_attempt(db: DBSession, key: str, window_seconds: int = 3600) -> None:
    """Record an attempt for key in the database and cheaply clean up expired entries on write."""
    try:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=window_seconds)

        # Delete expired entries for this key older than the window
        db.query(RateLimitEvent).filter(
            (RateLimitEvent.key == key) & (RateLimitEvent.created_at < cutoff)
        ).delete(synchronize_session=False)

        # Also purge any abandoned stale entries globally older than 24 hours
        global_cutoff = now - timedelta(hours=24)
        db.query(RateLimitEvent).filter(
            RateLimitEvent.created_at < global_cutoff
        ).delete(synchronize_session=False)

        db.expunge_all()

        event = RateLimitEvent(key=key, created_at=now)
        db.add(event)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error(f"Failed to record rate limit attempt for {key}: {type(exc).__name__}: {str(exc)}")


def clear_db_rate_limits(db: DBSession, key: Optional[str] = None) -> None:
    """Clear rate limit records from the database (useful for testing)."""
    try:
        query = db.query(RateLimitEvent)
        if key:
            query = query.filter(RateLimitEvent.key == key)
        query.delete(synchronize_session=False)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.debug(f"Error clearing rate limits: {exc}")


class InMemoryRateLimiter:
    """Thread-safe sliding-window in-memory rate limiter."""

    def __init__(self):
        self._lock = threading.Lock()
        self._attempts: Dict[str, List[float]] = defaultdict(list)

    def is_rate_limited(self, key: str, max_attempts: int, window_seconds: float) -> bool:
        """Check if key has reached or exceeded max_attempts within the window."""
        now = datetime.now(timezone.utc).timestamp()
        cutoff = now - window_seconds
        with self._lock:
            valid = [t for t in self._attempts[key] if t > cutoff]
            self._attempts[key] = valid
            return len(valid) >= max_attempts

    def record_attempt(self, key: str, window_seconds: float) -> None:
        """Record an attempt timestamp for key."""
        now = datetime.now(timezone.utc).timestamp()
        cutoff = now - window_seconds
        with self._lock:
            valid = [t for t in self._attempts[key] if t > cutoff]
            valid.append(now)
            self._attempts[key] = valid

    def reset(self, key: str) -> None:
        """Reset attempts for key (e.g. on successful login)."""
        with self._lock:
            self._attempts.pop(key, None)

    def clear(self) -> None:
        """Clear all rate limit records (useful for test suites)."""
        with self._lock:
            self._attempts.clear()


login_limiter = InMemoryRateLimiter()
forgot_password_limiter = InMemoryRateLimiter()

