from typing import Optional

from pydantic import BaseModel, Field


class LiveUpdate(BaseModel):
    active: bool = True
    session_id: Optional[int] = None
    posture: Optional[str] = Field(default=None, max_length=32)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    warnings: int = Field(default=0, ge=0)
    good_seconds: float = Field(default=0.0, ge=0)
    poor_seconds: float = Field(default=0.0, ge=0)