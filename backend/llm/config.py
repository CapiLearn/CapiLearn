from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="LLM_", extra="ignore"
    )

    model_profile_key: str = "default_tutor"
    model_profile_version: str = "2026-05-10"
    model: str = "openai/gpt-4o-mini"
    fallback_model: str | None = None
    temperature: float = 0.2
    max_tokens: int = 800
    request_timeout_seconds: float = 30.0
    guardrails_enabled: bool = True
    guardrails_config_id: str = "default"
    guardrails_config_path: Path | None = Path("backend/llm/guardrails/default")
    guardrails_model_engine: str = "litellm"
    guardrails_model: str = "openai/gpt-4o-mini"
    rag_index_version: str | None = Field(default=None)


@lru_cache
def get_llm_settings() -> LLMSettings:
    return LLMSettings()


llm_settings = get_llm_settings()
