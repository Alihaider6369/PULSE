"""Simple in-memory rate limiter for authentication endpoints."""
from collections import defaultdict
from datetime import datetime, timezone
import threading
from typing import Dict, List


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
