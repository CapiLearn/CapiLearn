from enum import StrEnum
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class InputGuardrailMode(StrEnum):
    POLICY = "policy"
    REGEX = "regex"
    OFF = "off"


class OutputGuardrailMode(StrEnum):
    POLICY = "policy"
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
    max_retries: int = Field(default=0, ge=0)
    retry_backoff_seconds: float = Field(default=0.5, ge=0)
    guardrails_enabled: bool = True
    input_guardrail_mode: InputGuardrailMode = InputGuardrailMode.POLICY
    output_guardrail_mode: OutputGuardrailMode = OutputGuardrailMode.POLICY
    guardrails_config_id: str = "default"
    guardrails_judge_enabled: bool = True
    guardrails_judge_model: str = "openai/gpt-4o-mini"
    guardrails_judge_temperature: float = 0
    guardrails_fail_open_on_judge_error: bool = True

    @field_validator("input_guardrail_mode", "output_guardrail_mode", mode="before")
    @classmethod
    def _map_legacy_guardrail_mode(cls, value: object) -> object:
        if isinstance(value, str) and value.lower() == "nemo":
            return "policy"
        return value


@lru_cache
def get_llm_settings() -> LLMSettings:
    return LLMSettings()


llm_settings = get_llm_settings()
