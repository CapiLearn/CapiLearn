from functools import lru_cache
from uuid import UUID

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "CapiLearn API"
    environment: str = "local"
    api_prefix: str = "/api"
    database_url: str = Field(
        default="postgresql+asyncpg://capilearn:capilearn@localhost:5432/capilearn",
        validation_alias="DATABASE_URL",
    )
    cors_origins: list[str] = Field(default_factory=list)
    local_dev_user_id: UUID = UUID("00000000-0000-0000-0000-000000000001")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
