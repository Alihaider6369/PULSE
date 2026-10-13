import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings


class Base(DeclarativeBase):
    """Parent class for all database tables (models)."""


def is_serverless_env() -> bool:
    """Detect if running inside a serverless environment like Vercel or AWS Lambda."""
    return bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))


# Use NullPool in serverless environments (Vercel) to prevent connection leaks on Neon PostgreSQL
if is_serverless_env():
    engine = create_engine(
        settings.sync_database_url,
        poolclass=NullPool,
    )
else:
    engine = create_engine(
        settings.sync_database_url,
        pool_pre_ping=True,
    )

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    """FastAPI dependency: gives one DB session per request, then closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()