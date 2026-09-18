from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND / ".env", extra="ignore", hide_input_in_errors=True
    )
    app_env: Literal["development", "testing", "production"] = "development"
    database_url: str = "postgresql+psycopg://care:change-me@localhost:5432/care"
    field_encryption_key: str = ""
    dev_auth_token: str = ""
    supabase_url: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"
    sarvam_api_key: str = ""
    sarvam_model: str = "saaras:v3"
    ocr_api_key: str = ""
    ocr_language: str = "eng"
    allowed_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "testserver", "api"]
    max_upload_bytes: int = 10 * 1024 * 1024
    provider_timeout: int = 45
    docs_enabled: bool = True

    @model_validator(mode="after")
    def validate_settings(self):
        if self.database_url.startswith(("postgres://", "postgresql://")):
            self.database_url = "postgresql+psycopg://" + self.database_url.split("://", 1)[1]
        if not self.field_encryption_key:
            raise ValueError("FIELD_ENCRYPTION_KEY is required. Run python3 scripts/setup.py.")
        if self.app_env == "production":
            if self.dev_auth_token or not self.supabase_url.startswith("https://"):
                raise ValueError(
                    "Production requires Supabase JWT authentication and DEV_AUTH_TOKEN must be empty."
                )
            if not self.database_url.startswith("postgresql") or self.docs_enabled:
                raise ValueError("Production requires PostgreSQL and DOCS_ENABLED=false.")
            if "*" in self.allowed_hosts or any(
                not s.startswith("https://") for s in self.allowed_origins
            ):
                raise ValueError("Production requires explicit hosts and HTTPS origins.")
        elif len(self.dev_auth_token) < 32:
            raise ValueError(
                "Development requires a random DEV_AUTH_TOKEN of at least 32 characters."
            )
        return self


@lru_cache
def get_settings():
    return Settings()
