"""Schemas for monitoring sessions and synchronization payloads."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SessionStart(BaseModel):
    session_code: str = Field(min_length=4, max_length=32)
    client_uuid: Optional[str] = Field(default=None, max_length=64)


class SessionEnd(BaseModel):
    good_seconds: float = Field(ge=0)
    poor_seconds: float = Field(ge=0)
    warning_count: int = Field(ge=0)


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: Optional[int] = None
    client_uuid: Optional[str] = None
    session_code: str
    started_at: datetime
    ended_at: Optional[datetime]
    duration_seconds: float
    good_seconds: float
    poor_seconds: float
    warning_count: int
    awareness_score: Optional[float]


# ---------------- Synchronization Schemas ----------------

class SyncEventIn(BaseModel):
    client_uuid: str = Field(min_length=1, max_length=64)
    occurred_at: datetime
    posture_class: str = Field(min_length=1, max_length=32)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    duration_seconds: float = Field(default=0.0, ge=0)
    is_warning: bool = False


class SyncSessionIn(BaseModel):
    client_uuid: str = Field(min_length=1, max_length=64)
    session_code: str = Field(min_length=1, max_length=32)
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_seconds: float = Field(default=0.0, ge=0)
    good_seconds: float = Field(default=0.0, ge=0)
    poor_seconds: float = Field(default=0.0, ge=0)
    warning_count: int = Field(default=0, ge=0)
    awareness_score: Optional[float] = None
    events: List[SyncEventIn] = []


class SyncPayload(BaseModel):
    sessions: List[SyncSessionIn] = Field(max_length=100)


class SyncResultItem(BaseModel):
    client_uuid: str
    server_id: int
    status: str = "ok"


class SyncResponse(BaseModel):
    synced: List[SyncResultItem]
    errors: List[Dict[str, Any]] = []