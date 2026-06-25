import pytest
from pydantic import ValidationError

from backend.llm import guardrail_factory as guardrail_factory_module
from backend.llm.config import InputGuardrailMode, LLMSettings, OutputGuardrailMode
from backend.llm.guardrails import (
    CompositeGuardrailsProvider,
    LLMJudgeGuardrailsProvider,
    NoopGuardrailsProvider,
    RegexGuardrailsProvider,
)


def test_llm_settings_guardrails_defaults(monkeypatch) -> None:
    monkeypatch.delenv("LLM_GUARDRAILS_ENABLED", raising=False)
    monkeypatch.delenv("LLM_INPUT_GUARDRAIL_MODE", raising=False)
    monkeypatch.delenv("LLM_OUTPUT_GUARDRAIL_MODE", raising=False)
    monkeypatch.delenv("LLM_GUARDRAILS_JUDGE_ENABLED", raising=False)
    monkeypatch.delenv("LLM_GUARDRAILS_JUDGE_MODEL", raising=False)
    monkeypatch.delenv("LLM_GUARDRAILS_JUDGE_TEMPERATURE", raising=False)
    monkeypatch.delenv("LLM_GUARDRAILS_FAIL_OPEN_ON_JUDGE_ERROR", raising=False)
    settings = LLMSettings(_env_file=None)

    assert settings.temperature is None
    assert settings.guardrails_enabled is True
    assert settings.input_guardrail_mode == InputGuardrailMode.POLICY
    assert settings.output_guardrail_mode == OutputGuardrailMode.POLICY
    assert settings.guardrails_judge_enabled is True
    assert settings.guardrails_judge_model == "openai/gpt-4o-mini"
    assert settings.guardrails_judge_temperature == 0
    assert settings.guardrails_fail_open_on_judge_error is True


def test_llm_settings_guardrails_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("LLM_GUARDRAILS_ENABLED", "false")
    monkeypatch.setenv("LLM_INPUT_GUARDRAIL_MODE", "regex")
    monkeypatch.setenv("LLM_OUTPUT_GUARDRAIL_MODE", "off")
    monkeypatch.setenv("LLM_GUARDRAILS_JUDGE_ENABLED", "false")
    monkeypatch.setenv("LLM_GUARDRAILS_JUDGE_MODEL", "custom-safety-model")
    monkeypatch.setenv("LLM_GUARDRAILS_JUDGE_TEMPERATURE", "0.2")
    monkeypatch.setenv("LLM_GUARDRAILS_FAIL_OPEN_ON_JUDGE_ERROR", "false")

    settings = LLMSettings(_env_file=None)

    assert settings.guardrails_enabled is False
    assert settings.input_guardrail_mode == InputGuardrailMode.REGEX
    assert settings.output_guardrail_mode == OutputGuardrailMode.OFF
    assert settings.guardrails_judge_enabled is False
    assert settings.guardrails_judge_model == "custom-safety-model"
    assert settings.guardrails_judge_temperature == 0.2
    assert settings.guardrails_fail_open_on_judge_error is False


def test_llm_settings_maps_legacy_nemo_guardrail_mode_to_policy(monkeypatch) -> None:
    monkeypatch.setenv("LLM_INPUT_GUARDRAIL_MODE", "nemo")
    monkeypatch.setenv("LLM_OUTPUT_GUARDRAIL_MODE", "nemo")

    settings = LLMSettings(_env_file=None)

    assert settings.input_guardrail_mode == InputGuardrailMode.POLICY
    assert settings.output_guardrail_mode == OutputGuardrailMode.POLICY


def test_llm_settings_rejects_invalid_guardrail_mode(monkeypatch) -> None:
    monkeypatch.setenv("LLM_INPUT_GUARDRAIL_MODE", "strict")

    with pytest.raises(ValidationError):
        LLMSettings(_env_file=None)


def test_global_guardrails_disable_builds_noop_guardrails(monkeypatch) -> None:
    settings = LLMSettings(
        _env_file=None,
        guardrails_enabled=False,
        input_guardrail_mode=InputGuardrailMode.POLICY,
        output_guardrail_mode=OutputGuardrailMode.POLICY,
    )
    monkeypatch.setattr(guardrail_factory_module, "llm_settings", settings)

    assert isinstance(guardrail_factory_module.build_input_guardrails(), NoopGuardrailsProvider)
    assert isinstance(guardrail_factory_module.build_output_guardrails(), NoopGuardrailsProvider)


def test_regex_input_mode_builds_regex_guardrails(monkeypatch) -> None:
    settings = LLMSettings(
        _env_file=None,
        input_guardrail_mode=InputGuardrailMode.REGEX,
    )
    monkeypatch.setattr(guardrail_factory_module, "llm_settings", settings)

    assert isinstance(guardrail_factory_module.build_input_guardrails(), RegexGuardrailsProvider)


def test_policy_input_mode_builds_composite_guardrails(monkeypatch) -> None:
    settings = LLMSettings(
        _env_file=None,
        input_guardrail_mode=InputGuardrailMode.POLICY,
        guardrails_judge_enabled=True,
    )
    monkeypatch.setattr(guardrail_factory_module, "llm_settings", settings)

    provider = guardrail_factory_module.build_input_guardrails()

    assert isinstance(provider, CompositeGuardrailsProvider)
    assert isinstance(provider.providers[0], RegexGuardrailsProvider)
    assert isinstance(provider.providers[1], LLMJudgeGuardrailsProvider)


def test_policy_input_mode_without_judge_builds_regex_guardrails(monkeypatch) -> None:
    settings = LLMSettings(
        _env_file=None,
        input_guardrail_mode=InputGuardrailMode.POLICY,
        guardrails_judge_enabled=False,
    )
    monkeypatch.setattr(guardrail_factory_module, "llm_settings", settings)

    assert isinstance(guardrail_factory_module.build_input_guardrails(), RegexGuardrailsProvider)


def test_policy_output_mode_builds_judge_guardrails(monkeypatch) -> None:
    settings = LLMSettings(
        _env_file=None,
        output_guardrail_mode=OutputGuardrailMode.POLICY,
        guardrails_judge_enabled=True,
    )
    monkeypatch.setattr(guardrail_factory_module, "llm_settings", settings)

    assert isinstance(
        guardrail_factory_module.build_output_guardrails(), LLMJudgeGuardrailsProvider
    )


def test_policy_output_mode_without_judge_builds_noop_guardrails(monkeypatch) -> None:
    settings = LLMSettings(
        _env_file=None,
        output_guardrail_mode=OutputGuardrailMode.POLICY,
        guardrails_judge_enabled=False,
    )
    monkeypatch.setattr(guardrail_factory_module, "llm_settings", settings)

    assert isinstance(guardrail_factory_module.build_output_guardrails(), NoopGuardrailsProvider)
