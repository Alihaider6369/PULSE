from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PostureEventIn(BaseModel):
    session_id: int
    posture_class: str = Field(min_length=1, max_length=32)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    duration_seconds: float = Field(default=0.0, ge=0)
    is_warning: bool = False


class PostureEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    occurred_at: datetime
    posture_class: str
    confidence: Optional[float]
    duration_seconds: float
    is_warning: bool