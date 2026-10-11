from sqlalchemy import Boolean, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class Setting(Base):
    """Single-row table with the monitor settings (id is always 1)."""

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    poor_posture_threshold_seconds: Mapped[float] = mapped_column(Float, default=30.0)
    cooldown_seconds: Mapped[float] = mapped_column(Float, default=300.0)
    warning_duration_seconds: Mapped[float] = mapped_column(Float, default=5.0)
    sound_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    min_confidence: Mapped[float] = mapped_column(Float, default=0.5)