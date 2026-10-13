import os
from pathlib import Path
from typing import List

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://pulse_user:password@localhost:5432/pulse_db"
    secret_key: str = ""
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days
    cors_origins: str = "http://localhost:8000,http://127.0.0.1:8000,http://localhost:3000"
    cookie_secure: bool = False
    environment: str = "development"

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_secret_key(self) -> "Settings":
        if not self.secret_key or not self.secret_key.strip():
            raise RuntimeError("SECRET_KEY environment variable is required")
        return self

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sync_database_url(self) -> str:
        """Return a normalized PostgreSQL connection URL compatible with SQLAlchemy 2.0 & Psycopg 3.

        - Normalizes legacy 'postgres://' or 'postgresql://' prefixes to 'postgresql+psycopg://'.
        - Preserves all existing query parameters.
        - Ensures 'sslmode=require' is present for remote hosts unless already explicitly specified.
        """
        raw_url = self.database_url
        if not raw_url:
            return raw_url

        # Normalize dialect scheme for psycopg 3
        if raw_url.startswith("postgres://"):
            raw_url = "postgresql+psycopg://" + raw_url[len("postgres://"):]
        elif raw_url.startswith("postgresql://") and not raw_url.startswith("postgresql+"):
            raw_url = "postgresql+psycopg://" + raw_url[len("postgresql://"):]

        parsed = urlparse(raw_url)

        # For remote PostgreSQL hosts, ensure sslmode is present while preserving all existing parameters
        if parsed.scheme.startswith("postgresql") and parsed.hostname not in (
            "localhost", "127.0.0.1", "db", None
        ):
            query_params = parse_qs(parsed.query, keep_blank_values=True)
            if "sslmode" not in query_params:
                query_params["sslmode"] = ["require"]
                new_query = urlencode(query_params, doseq=True)
                raw_url = urlunparse((
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path,
                    parsed.params,
                    new_query,
                    parsed.fragment,
                ))

        return raw_url


settings = Settings()