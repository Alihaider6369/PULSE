from typing import Optional

from sqlalchemy import Boolean, Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


class Setting(Base):
    """User-specific settings for the posture monitor."""

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=True
    )
    poor_posture_threshold_seconds: Mapped[float] = mapped_column(Float, default=30.0)
    cooldown_seconds: Mapped[float] = mapped_column(Float, default=300.0)
    warning_duration_seconds: Mapped[float] = mapped_column(Float, default=5.0)
    sound_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    min_confidence: Mapped[float] = mapped_column(Float, default=0.5)

    # Relationships
    user = relationship("User", back_populates="settings")