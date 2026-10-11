from datetime import datetime, timezone
from threading import Lock
from typing import Optional

_lock = Lock()
_state = {
    "active": False,
    "session_id": None,
    "posture": None,
    "confidence": None,
    "warnings": 0,
    "good_seconds": 0.0,
    "poor_seconds": 0.0,
    "updated_at": None,
}


def update(data: dict) -> dict:
    """Merge the latest values from the monitor into the shared state."""
    with _lock:
        _state.update({k: v for k, v in data.items() if k in _state})
        _state["updated_at"] = datetime.now(timezone.utc).isoformat()
        return dict(_state)


def get() -> dict:
    with _lock:
        return dict(_state)


def stop() -> dict:
    with _lock:
        _state["active"] = False
        _state["posture"] = None
        _state["updated_at"] = datetime.now(timezone.utc).isoformat()
        return dict(_state)