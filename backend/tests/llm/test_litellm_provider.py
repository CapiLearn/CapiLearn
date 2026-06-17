from decimal import Decimal

import pytest
from litellm import ServiceUnavailableError

from backend.llm import costing as llm_costing_module
from backend.llm import provider as llm_provider_module
from backend.llm.config import LLMSettings, llm_settings
from backend.llm.costing import LLMCostRecorder, cost_recorder_context
from backend.llm.provider import LiteLLMProvider
from backend.llm.schemas import ChatMessage, ChatRole
from backend.tests.llm.helpers import (
    _FakeEmptyLiteLLMResponse,
    _FakeLiteLLMResponse,
    _request,
)


@pytest.mark.asyncio
async def test_litellm_provider_uses_server_configured_model(monkeypatch) -> None:
    captured_kwargs = {}

    async def fake_acompletion(**kwargs):
        captured_kwargs.update(kwargs)
        return _FakeLiteLLMResponse()

    monkeypatch.setattr("backend.llm.provider.acompletion", fake_acompletion)

    provider = LiteLLMProvider()
    response = await provider.complete(
        [ChatMessage(role=ChatRole.USER, content="hello")],
    )

    assert response.content == "Configured model response."
    assert captured_kwargs["model"] == llm_settings.model
    assert "temperature" not in captured_kwargs
    assert "api_key" not in captured_kwargs


@pytest.mark.asyncio
async def test_litellm_provider_records_generation_cost_component(monkeypatch) -> None:
    async def fake_acompletion(**kwargs):
        return _FakeLiteLLMResponse()

    monkeypatch.setattr("backend.llm.provider.acompletion", fake_acompletion)
    monkeypatch.setattr(llm_costing_module, "completion_cost", lambda **kwargs: 0.001)

    request = _request("hello")
    recorder = LLMCostRecorder(
        user_id=str(request.user_id),
        conversation_id=str(request.conversation_id),
        user_message_id=str(request.user_message_id),
        assistant_message_id=str(request.assistant_message_id),
    )
    provider = LiteLLMProvider()
    with cost_recorder_context(recorder):
        await provider.complete([ChatMessage(role=ChatRole.USER, content="hello")])

    assert len(recorder.components) == 1
    component = recorder.components[0]
    assert component.component_type == "main_generation"
    assert component.prompt_tokens == 3
    assert component.completion_tokens == 4
    assert component.total_tokens == 7
    assert component.estimated_cost_usd == Decimal("0.001")
    assert component.status == "completed"


@pytest.mark.asyncio
async def test_litellm_provider_records_cost_unavailable_component(monkeypatch) -> None:
    async def fake_acompletion(**kwargs):
        return _FakeLiteLLMResponse()

    def fake_completion_cost(**kwargs):
        raise RuntimeError("unknown model")

    monkeypatch.setattr("backend.llm.provider.acompletion", fake_acompletion)
    monkeypatch.setattr(llm_costing_module, "completion_cost", fake_completion_cost)

    request = _request("hello")
    recorder = LLMCostRecorder(
        user_id=str(request.user_id),
        conversation_id=str(request.conversation_id),
        user_message_id=str(request.user_message_id),
        assistant_message_id=str(request.assistant_message_id),
    )
    provider = LiteLLMProvider()
    with cost_recorder_context(recorder):
        response = await provider.complete([ChatMessage(role=ChatRole.USER, content="hello")])

    assert response.content == "Configured model response."
    component = recorder.components[0]
    assert component.status == "cost_unavailable"
    assert component.estimated_cost_usd is None
    assert component.metadata["costError"] == "RuntimeError"


@pytest.mark.asyncio
async def test_litellm_provider_does_not_retry_transient_failure_by_default(
    monkeypatch,
) -> None:
    calls = 0

    async def fake_acompletion(**kwargs):
        nonlocal calls
        calls += 1
        raise ServiceUnavailableError(
            "provider unavailable",
            llm_provider="gemini",
            model=llm_settings.model,
        )

    settings = LLMSettings(_env_file=None, max_retries=0)

    monkeypatch.setattr("backend.llm.provider.acompletion", fake_acompletion)
    monkeypatch.setattr(llm_provider_module, "llm_settings", settings)

    provider = LiteLLMProvider()
    with pytest.raises(ServiceUnavailableError):
        await provider.complete([ChatMessage(role=ChatRole.USER, content="hello")])

    assert calls == 1


@pytest.mark.asyncio
async def test_litellm_provider_retries_transient_provider_failure_when_configured(
    monkeypatch,
) -> None:
    calls = 0

    async def fake_acompletion(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ServiceUnavailableError(
                "provider unavailable",
                llm_provider="gemini",
                model=llm_settings.model,
            )
        return _FakeLiteLLMResponse()

    async def fake_sleep(delay):
        return None

    settings = LLMSettings(_env_file=None, max_retries=1)

    monkeypatch.setattr("backend.llm.provider.acompletion", fake_acompletion)
    monkeypatch.setattr(llm_provider_module, "llm_settings", settings)
    monkeypatch.setattr(llm_provider_module.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(llm_costing_module, "completion_cost", lambda **kwargs: 0.001)

    request = _request("hello")
    recorder = LLMCostRecorder(
        user_id=str(request.user_id),
        conversation_id=str(request.conversation_id),
        user_message_id=str(request.user_message_id),
        assistant_message_id=str(request.assistant_message_id),
    )
    provider = LiteLLMProvider()
    with cost_recorder_context(recorder):
        response = await provider.complete([ChatMessage(role=ChatRole.USER, content="hello")])

    assert response.content == "Configured model response."
    assert calls == 2
    assert [component.attempt_index for component in recorder.components] == [1, 2]
    assert [component.status for component in recorder.components] == ["failed", "completed"]


@pytest.mark.asyncio
async def test_litellm_provider_sends_configured_temperature(monkeypatch) -> None:
    captured_kwargs = {}
    settings = LLMSettings(_env_file=None, temperature=0.2)

    async def fake_acompletion(**kwargs):
        captured_kwargs.update(kwargs)
        return _FakeLiteLLMResponse()

    monkeypatch.setattr("backend.llm.provider.acompletion", fake_acompletion)
    monkeypatch.setattr(llm_provider_module, "llm_settings", settings)

    provider = LiteLLMProvider()
    await provider.complete([ChatMessage(role=ChatRole.USER, content="hello")])

    assert captured_kwargs["temperature"] == 0.2


@pytest.mark.asyncio
async def test_litellm_provider_rejects_empty_choices(monkeypatch) -> None:
    async def fake_acompletion(**kwargs):
        return _FakeEmptyLiteLLMResponse()

    monkeypatch.setattr("backend.llm.provider.acompletion", fake_acompletion)

    provider = LiteLLMProvider()

    with pytest.raises(
        RuntimeError,
        match="LLM provider returned a response with no choices.",
    ):
        await provider.complete([ChatMessage(role=ChatRole.USER, content="hello")])
