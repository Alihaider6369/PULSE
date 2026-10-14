
import os
from pathlib import Path
from typing import List
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = (
        "postgresql+psycopg://pulse_user:password@localhost:5432/pulse_db"
    )

    secret_key: str = ""
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7

    cors_origins: str = (
        "http://localhost:8000,"
        "http://127.0.0.1:8000,"
        "http://localhost:3000"
    )

    cookie_secure: bool = False
    environment: str = "development"

    upstash_redis_rest_url: str = Field(
        default="",
        validation_alias=AliasChoices(
            "UPSTASH_REDIS_REST_URL",
            "KV_REST_API_URL",
            "upstash_redis_rest_url",
            "kv_rest_api_url",
        ),
    )
    upstash_redis_rest_token: str = Field(
        default="",
        validation_alias=AliasChoices(
            "UPSTASH_REDIS_REST_TOKEN",
            "KV_REST_API_TOKEN",
            "upstash_redis_rest_token",
            "kv_rest_api_token",
        ),
    )
    redis_url: str = Field(
        default="",
        validation_alias=AliasChoices(
            "REDIS_URL",
            "KV_URL",
            "redis_url",
            "kv_url",
        ),
    )
    live_status_ttl_seconds: int = 15

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    app_base_url: str = "http://127.0.0.1:8000"

    @field_validator("smtp_port", mode="before")
    @classmethod
    def parse_smtp_port(cls, v):
        if v is None or v == "":
            return 587
        return int(v)

    @field_validator("app_base_url", mode="before")
    @classmethod
    def parse_app_base_url(cls, v):
        if not v or not str(v).strip():
            return "http://127.0.0.1:8000"
        return str(v).strip()

    @model_validator(mode="after")
    def validate_secret_key(self) -> "Settings":
        key = (self.secret_key or "").strip()
        if not key:
            raise RuntimeError(
                "SECRET_KEY environment variable is required"
            )
        insecure_keys = {
            "secret",
            "secret_key",
            "password",
            "changethis",
            "change_this",
            "replace_with_cryptographically_secure_hex_string_min_64_chars",
        }
        if key.lower() in insecure_keys:
            raise RuntimeError(
                "SECRET_KEY cannot be a default or placeholder value"
            )
        is_prod = self.environment == "production" or bool(os.environ.get("VERCEL"))
        if is_prod and len(key) < 32:
            raise RuntimeError(
                "SECRET_KEY must be at least 32 characters long in production/serverless"
            )
        return self

    @model_validator(mode="after")
    def validate_database_url(self) -> "Settings":
        db_url = (self.database_url or "").strip()
        is_prod = self.environment == "production" or bool(os.environ.get("VERCEL"))
        if is_prod:
            if not db_url:
                raise RuntimeError(
                    "DATABASE_URL environment variable is required in production/serverless"
                )
            if db_url.startswith("sqlite:"):
                raise RuntimeError(
                    "SQLite is not supported in production/serverless environments. "
                    "Configure a remote PostgreSQL database (such as Neon) in DATABASE_URL."
                )
            if (
                "pulse_user:password@localhost" in db_url
                or "localhost:5432" in db_url
                or "127.0.0.1:5432" in db_url
            ):
                raise RuntimeError(
                    "DATABASE_URL is set to local default. In production/serverless, "
                    "a remote managed PostgreSQL database (such as Neon) is required."
                )
            if not (
                db_url.startswith("postgresql://")
                or db_url.startswith("postgresql+")
                or db_url.startswith("postgres://")
            ):
                raise RuntimeError(
                    "DATABASE_URL must use the postgresql:// or postgresql+psycopg:// scheme in production."
                )
        return self

    @model_validator(mode="after")
    def validate_smtp_config(self) -> "Settings":
        if self.smtp_host and self.smtp_host.strip():
            if (
                not self.smtp_user
                or not self.smtp_user.strip()
                or not self.smtp_password
                or not self.smtp_password.strip()
            ):
                raise RuntimeError(
                    "SMTP_USER and SMTP_PASSWORD are required "
                    "when SMTP_HOST is configured"
                )
        return self

    @property
    def effective_smtp_from(self) -> str:
        return (
            self.smtp_from.strip()
            if self.smtp_from.strip()
            else self.smtp_user.strip()
        )

    @property
    def cors_origin_list(self) -> List[str]:
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]

    @property
    def effective_upstash_url(self) -> str:
        return (
            self.upstash_redis_rest_url.strip()
            or os.environ.get("KV_REST_API_URL", "").strip()
        )

    @property
    def effective_upstash_token(self) -> str:
        return (
            self.upstash_redis_rest_token.strip()
            or os.environ.get("KV_REST_API_TOKEN", "").strip()
        )

    @property
    def effective_redis_url(self) -> str:
        return (
            self.redis_url.strip()
            or os.environ.get("KV_URL", "").strip()
        )

    @property
    def sync_database_url(self) -> str:
        """Normalize PostgreSQL URLs for SQLAlchemy and Psycopg 3."""

        raw_url = self.database_url.strip()

        if not raw_url:
            return raw_url

        if raw_url.startswith("postgres://"):
            raw_url = (
                "postgresql+psycopg://"
                + raw_url[len("postgres://"):]
            )
        elif (
            raw_url.startswith("postgresql://")
            and not raw_url.startswith("postgresql+")
        ):
            raw_url = (
                "postgresql+psycopg://"
                + raw_url[len("postgresql://"):]
            )

        parsed = urlparse(raw_url)

        if (
            parsed.scheme.startswith("postgresql")
            and parsed.hostname not in (
                "localhost",
                "127.0.0.1",
                "db",
                None,
            )
        ):
            query_params = parse_qs(
                parsed.query,
                keep_blank_values=True,
            )

            if "sslmode" not in query_params:
                query_params["sslmode"] = ["require"]

                raw_url = urlunparse((
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path,
                    parsed.params,
                    urlencode(query_params, doseq=True),
                    parsed.fragment,
                ))

        return raw_url


settings = Settings()
