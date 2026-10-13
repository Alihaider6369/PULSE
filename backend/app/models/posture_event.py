from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


class PostureEvent(Base):
    """One posture state change or warning, linked to a monitoring session."""

    __tablename__ = "posture_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    client_uuid: Mapped[Optional[str]] = mapped_column(
        String(64), unique=True, index=True, nullable=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    posture_class: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    is_warning: Mapped[bool] = mapped_column(default=False)

    # Relationships
    session = relationship("Session", back_populates="events")