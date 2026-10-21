"""Rate limiting events model for database-backed rate limiting."""
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, func
from app.database.session import Base


class RateLimitEvent(Base):
    """Database-backed counter event for serverless rate limiting."""

    __tablename__ = "rate_limit_events"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(255), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
