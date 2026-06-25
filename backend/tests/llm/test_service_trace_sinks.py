import logging

import pytest

from backend.core.observability import BestEffortLLMTraceSink, NoopLLMTraceSink
from backend.llm.service import LLMService
from backend.rag.trace_contracts import BestEffortRetrievalTraceSink
from backend.tests.llm.helpers import (
    AllowGuardrails,
    FailingRetrievalTraceSink,
    FailingTraceSink,
    FakeProvider,
    FakeRetriever,
    IncompleteTraceSink,
    RepairableOutputGuardrails,
    SequenceProvider,
    _events,
    _request,
)


@pytest.mark.asyncio
async def test_llm_service_default_trace_sink_is_explicit_noop() -> None:
    service = LLMService(
        provider=FakeProvider(),
        guardrails=AllowGuardrails(),
    )

    assert isinstance(service._trace_sink, NoopLLMTraceSink)


@pytest.mark.asyncio
async def test_llm_service_incomplete_trace_sink_cannot_be_constructed() -> None:
    with pytest.raises(TypeError):
        IncompleteTraceSink()


@pytest.mark.asyncio
async def test_llm_service_trace_sink_failures_do_not_change_result(caplog) -> None:
    caplog.set_level(logging.WARNING, logger="backend.core.observability.tracing")
    provider = FakeProvider()
    service = LLMService(
        provider=provider,
        guardrails=AllowGuardrails(),
        retriever=FakeRetriever(),
        trace_sink=BestEffortLLMTraceSink(FailingTraceSink()),
    )

    result = await service.complete(_request("What is photosynthesis?"))

    assert result.content == "Plants turn light into energy."
    assert result.retrieved_context[0].metadata["source_id"] == "doc_1"
    assert provider.complete_called
    failed_events = _events(caplog.records, "trace_sink.failed")
    assert {record.trace_operation for record in failed_events} >= {
        "record_guardrail",
        "record_generation",
    }


@pytest.mark.asyncio
async def test_llm_service_retrieval_trace_sink_failures_do_not_change_result(caplog) -> None:
    caplog.set_level(logging.WARNING, logger="backend.rag.trace_contracts")
    provider = FakeProvider()
    service = LLMService(
        provider=provider,
        guardrails=AllowGuardrails(),
        retriever=FakeRetriever(),
        retrieval_trace_sink=BestEffortRetrievalTraceSink(FailingRetrievalTraceSink()),
    )

    result = await service.complete(_request("What is photosynthesis?"))

    assert result.content == "Plants turn light into energy."
    assert provider.complete_called
    failed_events = _events(caplog.records, "trace_sink.failed")
    assert failed_events[-1].trace_operation == "record_retrieval"
    assert failed_events[-1].sink_type == "FailingRetrievalTraceSink"


@pytest.mark.asyncio
async def test_llm_service_trace_sink_failures_do_not_block_repair_result() -> None:
    provider = SequenceProvider(
        [
            "The direct answer is 42.",
            "What is the first relationship you can write from the problem?",
        ]
    )
    service = LLMService(
        provider=provider,
        guardrails=RepairableOutputGuardrails(),
        retriever=FakeRetriever(),
        trace_sink=BestEffortLLMTraceSink(FailingTraceSink()),
    )

    result = await service.complete(_request("Solve this homework problem."))

    assert result.content == ("What is the first relationship you can write from the problem?")
    assert not result.output_guardrail_result.blocked
    assert result.output_guardrail_result.metadata["repairPassed"] is True
    assert len(provider.calls) == 2
