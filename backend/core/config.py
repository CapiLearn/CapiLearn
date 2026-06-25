"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_VALID_LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
_MAX_DEMO_ADMIN_SIGN_IN_TOKEN_TTL_SECONDS = 300


class Settings(BaseSettings):
    """Runtime settings shared by the backend application."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "CapiLearn API"
    environment: str = "local"
    api_prefix: str = "/api"
    api_docs_enabled: bool = False
    log_level: str = "INFO"
    log_format: Literal["json", "plain"] = "json"
    request_id_header: str = "X-Request-Id"
    observability_enabled: bool = True
    observability_capture_content: bool = False
    database_url: str = Field(
        default="postgresql+asyncpg://capilearn:capilearn@localhost:5432/capilearn",
        validation_alias="DATABASE_URL",
    )
    cors_origins: list[str] = Field(default_factory=list)
    clerk_secret_key: str | None = None
    clerk_jwt_key: str | None = None
    clerk_webhook_signing_secret: str | None = None
    clerk_authorized_parties: list[str] = Field(default_factory=list)
    demo_admin_login_enabled: bool = False
    demo_admin_clerk_user_id: str | None = None
    demo_admin_sign_in_token_ttl_seconds: int = 60
    auth_mode: Literal["clerk", "test"] = "clerk"
    test_auth_clerk_id: str = "user_local_dev"
    test_auth_first_name: str | None = "Local"
    test_auth_last_name: str | None = "Dev"
    test_auth_role: Literal["student", "instructor", "admin"] = "student"

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        """Normalize log levels and reject values unsupported by logging."""
        normalized = value.upper()
        if normalized not in _VALID_LOG_LEVELS:
            raise ValueError(f"log_level must be one of: {', '.join(sorted(_VALID_LOG_LEVELS))}")
        return normalized

    @field_validator("demo_admin_sign_in_token_ttl_seconds")
    @classmethod
    def validate_demo_admin_sign_in_token_ttl_seconds(cls, value: int) -> int:
        if value < 1:
            raise ValueError("demo_admin_sign_in_token_ttl_seconds must be at least 1 second")
        return min(value, _MAX_DEMO_ADMIN_SIGN_IN_TOKEN_TTL_SECONDS)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()


settings = get_settings()
