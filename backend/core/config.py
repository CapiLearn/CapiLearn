from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_VALID_LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "CapiLearn API"
    environment: str = "local"
    api_prefix: str = "/api"
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
    clerk_authorized_parties: list[str] = Field(default_factory=list)
    auth_mode: Literal["clerk", "test"] = "clerk"
    test_auth_clerk_id: str = "user_local_dev"
    test_auth_email: str | None = None
    test_auth_display_name: str | None = None
    test_auth_role: Literal["student", "instructor", "admin"] = "student"

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in _VALID_LOG_LEVELS:
            raise ValueError(f"log_level must be one of: {', '.join(sorted(_VALID_LOG_LEVELS))}")
        return normalized


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
