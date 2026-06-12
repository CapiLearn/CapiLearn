from functools import lru_cache
from typing import Literal
from uuid import UUID

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    beta_auth_enabled: bool = False
    beta_auth_username: SecretStr | None = None
    beta_auth_password: SecretStr | None = None
    database_url: str = Field(
        default="postgresql+asyncpg://capilearn:capilearn@localhost:5432/capilearn",
        validation_alias="DATABASE_URL",
    )
    cors_origins: list[str] = Field(default_factory=list)
    local_dev_user_id: UUID = UUID("00000000-0000-0000-0000-000000000001")

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: object) -> object:
        if isinstance(value, str):
            return normalize_async_database_url(value)
        return value

    @model_validator(mode="after")
    def validate_beta_auth_credentials(self) -> "Settings":
        if not self.beta_auth_enabled:
            return self

        missing = []
        if not self.beta_auth_username or not self.beta_auth_username.get_secret_value().strip():
            missing.append("BETA_AUTH_USERNAME")
        if not self.beta_auth_password or not self.beta_auth_password.get_secret_value().strip():
            missing.append("BETA_AUTH_PASSWORD")

        if missing:
            names = " and ".join(missing)
            raise ValueError(f"{names} must be set when BETA_AUTH_ENABLED=true")

        return self


def normalize_async_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    return database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
