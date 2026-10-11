from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class Session(Base):
    """One monitoring run, from start to stop."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    good_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    poor_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    awareness_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)