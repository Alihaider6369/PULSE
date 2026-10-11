from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SessionStart(BaseModel):
    session_code: str = Field(min_length=4, max_length=16)


class SessionEnd(BaseModel):
    good_seconds: float = Field(ge=0)
    poor_seconds: float = Field(ge=0)
    warning_count: int = Field(ge=0)


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_code: str
    started_at: datetime
    ended_at: Optional[datetime]
    duration_seconds: float
    good_seconds: float
    poor_seconds: float
    warning_count: int
    awareness_score: Optional[float]