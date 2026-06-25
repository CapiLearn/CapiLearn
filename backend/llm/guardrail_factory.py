"""Factories for configured LLM guardrail providers."""

from backend.llm.config import InputGuardrailMode, OutputGuardrailMode, llm_settings
from backend.llm.guardrails import (
    CompositeGuardrailsProvider,
    LLMJudgeGuardrailsProvider,
    NoopGuardrailsProvider,
    RegexGuardrailsProvider,
)
from backend.llm.schemas import GuardrailsProvider


def build_input_guardrails() -> GuardrailsProvider:
    """Build the configured input guardrail chain."""

    if not llm_settings.guardrails_enabled:
        return NoopGuardrailsProvider()
    if llm_settings.input_guardrail_mode == InputGuardrailMode.OFF:
        return NoopGuardrailsProvider()
    if llm_settings.input_guardrail_mode == InputGuardrailMode.REGEX:
        return RegexGuardrailsProvider()
    if not llm_settings.guardrails_judge_enabled:
        return RegexGuardrailsProvider()
    return CompositeGuardrailsProvider(
        [
            RegexGuardrailsProvider(),
            _build_llm_judge_guardrails(),
        ]
    )


def build_output_guardrails() -> GuardrailsProvider:
    """Build the configured output guardrail provider."""

    if (
        not llm_settings.guardrails_enabled
        or llm_settings.output_guardrail_mode == OutputGuardrailMode.OFF
        or not llm_settings.guardrails_judge_enabled
    ):
        return NoopGuardrailsProvider()
    return _build_llm_judge_guardrails()


def _build_llm_judge_guardrails() -> LLMJudgeGuardrailsProvider:
    return LLMJudgeGuardrailsProvider(
        model=llm_settings.guardrails_judge_model,
        temperature=llm_settings.guardrails_judge_temperature,
        timeout=llm_settings.request_timeout_seconds,
        fail_open_on_error=llm_settings.guardrails_fail_open_on_judge_error,
    )
