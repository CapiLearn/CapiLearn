import logging

import pytest

from backend.llm import costing as llm_costing_module
from backend.llm.guardrails import LLMJudgeGuardrailsProvider, NoopGuardrailsProvider
from backend.llm.provider import LiteLLMProvider
from backend.llm.service import LLMService, LLMServiceError
from backend.tests.llm.helpers import (
    AllowGuardrails,
    BlockingInputGuardrails,
    BlockingOutputGuardrails,
    FailingInputGuardrails,
    FakeProvider,
    FakeRetriever,
    RecordingTraceSink,
    RepairableOutputGuardrails,
    SequenceProvider,
    _events,
    _FakeLiteLLMResponse,
    _judge_response,
    _request,
)


@pytest.mark.asyncio
async def test_llm_service_blocks_unsafe_input_before_provider_call(caplog) -> None:
    caplog.set_level(logging.INFO, logger="backend.llm.service")
    provider = FakeProvider()
    service = LLMService(
        provider=provider,
        guardrails=BlockingInputGuardrails(),
        retriever=FakeRetriever(),
    )

    result = await service.complete(_request("bad input"))

    assert result.input_guardrail_result.blocked
    assert result.content == "Input blocked."
    assert provider.messages == []
    assert not provider.complete_called
    guardrail_events = _events(caplog.records, "guardrail.check.completed")
    assert guardrail_events[-1].guardrail_stage == "input"
    assert guardrail_events[-1].blocked is True


@pytest.mark.asyncio
async def test_llm_service_blocks_unsafe_output_after_provider_call() -> None:
    provider = FakeProvider()
    service = LLMService(
        provider=provider,
        guardrails=BlockingOutputGuardrails(),
        retriever=FakeRetriever(),
    )

    result = await service.complete(_request("safe input"))

    assert result.output_guardrail_result.blocked
    assert result.content == "Output blocked."
    assert provider.complete_called


@pytest.mark.asyncio
async def test_llm_service_can_skip_output_guardrail() -> None:
    provider = FakeProvider()
    service = LLMService(
        provider=provider,
        input_guardrails=AllowGuardrails(),
        output_guardrails=NoopGuardrailsProvider(),
        retriever=FakeRetriever(),
    )

    result = await service.complete(_request("safe input"))

    assert not result.output_guardrail_result.blocked
    assert result.content == "Plants turn light into energy."
    assert provider.complete_called


@pytest.mark.asyncio
async def test_llm_service_repairs_blocked_direct_answer_output(caplog) -> None:
    caplog.set_level(logging.INFO, logger="backend.llm.service")
    provider = SequenceProvider(
        [
            "The direct answer is 42.",
            "What is the first relationship you can write from the problem?",
        ]
    )
    trace_sink = RecordingTraceSink()
    service = LLMService(
        provider=provider,
        guardrails=RepairableOutputGuardrails(),
        retriever=FakeRetriever(),
        trace_sink=trace_sink,
    )

    result = await service.complete(_request("Solve this homework problem."))

    assert result.content == ("What is the first relationship you can write from the problem?")
    assert not result.output_guardrail_result.blocked
    assert result.output_guardrail_result.metadata["repairAttempted"] is True
    assert result.output_guardrail_result.metadata["repairPassed"] is True
    assert (
        result.output_guardrail_result.metadata["initialOutputGuardrailResult"]["blocked"] is True
    )
    assert len(provider.calls) == 2
    assert "Draft assistant response to repair" in provider.calls[1][-1].content
    repair_events = _events(caplog.records, "chat.repair.completed")
    assert repair_events
    assert repair_events[-1].repair_passed is True
    assert [generation["generation_stage"] for generation in trace_sink.generations] == [
        "primary",
        "repair",
    ]
    assert trace_sink.repairs[-1]["repair_passed"] is True


@pytest.mark.asyncio
async def test_llm_service_records_repair_flow_cost_components(monkeypatch) -> None:
    responses = [
        _judge_response(blocked=False, rail="input_policy"),
        _FakeLiteLLMResponse(content="The direct answer is 42."),
        _judge_response(blocked=True, rail="output_policy", reason="Direct answer."),
        _FakeLiteLLMResponse(
            content="What is the first relationship you can write from the problem?"
        ),
        _judge_response(blocked=False, rail="output_policy"),
    ]

    async def fake_acompletion(**kwargs):
        return responses.pop(0)

    monkeypatch.setattr("backend.llm.provider.acompletion", fake_acompletion)
    monkeypatch.setattr(llm_costing_module, "completion_cost", lambda **kwargs: 0.0001)
    service = LLMService(
        provider=LiteLLMProvider(),
        input_guardrails=LLMJudgeGuardrailsProvider(
            model="openai/gpt-4o-mini",
            completion=fake_acompletion,
        ),
        output_guardrails=LLMJudgeGuardrailsProvider(
            model="openai/gpt-4o-mini",
            completion=fake_acompletion,
        ),
        retriever=FakeRetriever(),
    )

    result = await service.complete(_request("Solve this homework problem."))

    assert result.content == "What is the first relationship you can write from the problem?"
    assert [component.component_type for component in result.cost_components] == [
        "input_guardrail",
        "main_generation",
        "output_guardrail",
        "repair_generation",
        "output_repair_guardrail",
    ]
    assert [component.component_order for component in result.cost_components] == [1, 2, 3, 4, 5]


@pytest.mark.asyncio
async def test_llm_service_error_exposes_failed_cost_components(monkeypatch, caplog) -> None:
    caplog.set_level(logging.ERROR, logger="backend.llm.service")

    async def fake_acompletion(**kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr("backend.llm.provider.acompletion", fake_acompletion)
    service = LLMService(
        provider=LiteLLMProvider(),
        input_guardrails=AllowGuardrails(),
        output_guardrails=NoopGuardrailsProvider(),
        retriever=FakeRetriever(),
    )

    with pytest.raises(LLMServiceError) as exc_info:
        await service.complete(_request("What is photosynthesis?"))

    assert isinstance(exc_info.value.original_exception, RuntimeError)
    assert len(exc_info.value.cost_components) == 1
    component = exc_info.value.cost_components[0]
    assert component.component_type == "main_generation"
    assert component.status == "failed"
    assert component.error_type == "RuntimeError"
    assert component.estimated_cost_usd is None
    failed_events = _events(caplog.records, "llm.generation.failed")
    assert failed_events[-1].exc_info[0] is RuntimeError
    assert failed_events[-1].exc_info[1] is exc_info.value.original_exception


@pytest.mark.asyncio
async def test_llm_service_guardrail_error_log_includes_exception_info(caplog) -> None:
    caplog.set_level(logging.ERROR, logger="backend.llm.service")
    provider = FakeProvider()
    service = LLMService(
        provider=provider,
        guardrails=FailingInputGuardrails(),
        retriever=FakeRetriever(),
    )

    with pytest.raises(LLMServiceError) as exc_info:
        await service.complete(_request("What is photosynthesis?"))

    assert isinstance(exc_info.value.original_exception, RuntimeError)
    assert not provider.complete_called
    failed_events = _events(caplog.records, "guardrail.check.failed")
    assert failed_events[-1].guardrail_stage == "input"
    assert failed_events[-1].exc_info[0] is RuntimeError


@pytest.mark.asyncio
async def test_llm_service_blocks_output_when_repair_still_fails() -> None:
    provider = SequenceProvider(
        [
            "The direct answer is 42.",
            "The direct answer is still 42.",
        ]
    )
    service = LLMService(
        provider=provider,
        guardrails=RepairableOutputGuardrails(),
        retriever=FakeRetriever(),
    )

    result = await service.complete(_request("Solve this homework problem."))

    assert result.output_guardrail_result.blocked
    assert result.content == "Output blocked."
    assert result.output_guardrail_result.metadata["repairAttempted"] is True
    assert result.output_guardrail_result.metadata["repairPassed"] is False
    assert len(provider.calls) == 2
