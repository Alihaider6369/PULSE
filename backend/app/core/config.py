
from pathlib import Path
from typing import List
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from pydantic import field_validator, model_validator
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
        if not self.secret_key or not self.secret_key.strip():
            raise RuntimeError(
                "SECRET_KEY environment variable is required"
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
