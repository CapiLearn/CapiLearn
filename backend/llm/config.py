from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class InputGuardrailMode(StrEnum):
    NEMO = "nemo"
    REGEX = "regex"
    OFF = "off"


class OutputGuardrailMode(StrEnum):
    NEMO = "nemo"
    OFF = "off"


class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="LLM_", extra="ignore")

    model_profile_key: str = "default_tutor"
    model_profile_version: str = "2026-05-10"
    model: str = "openai/gpt-4o-mini"
    fallback_model: str | None = None
    temperature: float | None = None
    max_tokens: int = 8000
    request_timeout_seconds: float = 30.0
    guardrails_enabled: bool = True
    input_guardrail_mode: InputGuardrailMode = InputGuardrailMode.NEMO
    output_guardrail_mode: OutputGuardrailMode = OutputGuardrailMode.NEMO
    guardrails_config_id: str = "default"
    guardrails_config_path: Path | None = Path("backend/llm/guardrails/default")
    regex_guardrails_config_path: Path = Path("backend/llm/guardrails/regex")
    guardrails_model_engine: str = "litellm"
    guardrails_model: str = "openai/gpt-4o-mini"
    rag_index_version: str | None = Field(default=None)


@lru_cache
def get_llm_settings() -> LLMSettings:
    return LLMSettings()


llm_settings = get_llm_settings()
