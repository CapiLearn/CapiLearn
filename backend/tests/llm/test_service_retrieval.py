import asyncio
import logging

import pytest

from backend.llm.prompts import BASE_SYSTEM_PROMPT
from backend.llm.schemas import ChatRole
from backend.llm.service import LLMService
from backend.rag.schemas import RagRetrievalLogRecord, RetrievedChunk
from backend.tests.llm.helpers import (
    AllowGuardrails,
    CoordinatedRetriever,
    FailingRetriever,
    FakeProvider,
    FakeRetriever,
    RecordingRetrievalTraceSink,
    RecordingTraceSink,
    ReleasableRetriever,
    RichChunkRetriever,
    WaitForRetrievalDoneGuardrails,
    WaitForRetrievalGuardrails,
    _events,
    _request,
)


@pytest.mark.asyncio
async def test_llm_service_adds_retrieved_context_to_user_message(caplog) -> None:
    caplog.set_level(logging.INFO, logger="backend.llm.service")
    provider = FakeProvider()
    service = LLMService(
        provider=provider,
        guardrails=AllowGuardrails(),
        retriever=FakeRetriever(),
    )

    result = await service.complete(_request("What is photosynthesis?"))

    assert result.content == "Plants turn light into energy."
    assert result.retrieved_context[0].metadata["source_id"] == "doc_1"
    assert "citations" not in result.model_dump()
    assert provider.messages[0].role == ChatRole.SYSTEM
    assert provider.messages[0].content == BASE_SYSTEM_PROMPT
    assert provider.messages[-1].role == ChatRole.USER
    assert "Relevant note for: What is photosynthesis?" in provider.messages[-1].content
    assert "Biology Notes - doc_1 - page 3" in provider.messages[-1].content
    assert "<retrieved_context>" in provider.messages[-1].content
    assert "<student_message>\nWhat is photosynthesis?" in provider.messages[-1].content
    assert _events(caplog.records, "guardrail.check.completed")
    retrieval_events = _events(caplog.records, "rag.retrieve.completed")
    assert retrieval_events[-1].chunk_count == 1
    assert "Relevant note for" not in caplog.text
    assert _events(caplog.records, "llm.generation.completed")


@pytest.mark.asyncio
async def test_llm_service_sends_typed_record_to_retrieval_trace_sink() -> None:
    retrieval_trace_sink = RecordingRetrievalTraceSink()
    provider = FakeProvider()
    service = LLMService(
        provider=provider,
        guardrails=AllowGuardrails(),
        retriever=FakeRetriever(),
        retrieval_trace_sink=retrieval_trace_sink,
    )

    result = await service.complete(_request("What is photosynthesis?"))

    assert result.content == "Plants turn light into energy."
    assert provider.complete_called
    assert isinstance(retrieval_trace_sink.records[-1], RagRetrievalLogRecord)
    assert retrieval_trace_sink.records[-1].query_text == "What is photosynthesis?"


@pytest.mark.asyncio
async def test_llm_service_accepts_retrieval_result_contract() -> None:
    provider = FakeProvider()
    service = LLMService(
        provider=provider,
        guardrails=AllowGuardrails(),
        retriever=RichChunkRetriever(),
    )

    result = await service.complete(_request("What is photosynthesis?"))

    assert result.retrieved_context == [
        RetrievedChunk(
            content="Rich note for: What is photosynthesis?",
            metadata={
                "source_id": "doc_1",
                "title": "Biology Notes",
            },
            distance=0.12,
        )
    ]
    assert result.retrieved_context[0].model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
    ) == {
        "content": "Rich note for: What is photosynthesis?",
        "metadata": {
            "source_id": "doc_1",
            "title": "Biology Notes",
        },
        "distance": 0.12,
    }
    assert "Rich note for: What is photosynthesis?" in provider.messages[-1].content
    assert result.retrieved_context[0].distance == 0.12


@pytest.mark.asyncio
async def test_llm_service_omits_retrieved_context_block_without_chunks() -> None:
    provider = FakeProvider()
    service = LLMService(
        provider=provider,
        guardrails=AllowGuardrails(),
    )

    result = await service.complete(_request("What is photosynthesis?"))

    assert result.retrieved_context == []
    assert provider.messages[-1].role == ChatRole.USER
    assert "<retrieved_context>" not in provider.messages[-1].content
    assert provider.messages[-1].content == (
        "<student_message>\nWhat is photosynthesis?\n</student_message>"
    )


@pytest.mark.asyncio
async def test_llm_service_system_prompt_is_static_across_retrievals() -> None:
    provider = FakeProvider()
    service = LLMService(
        provider=provider,
        guardrails=AllowGuardrails(),
        retriever=FakeRetriever(),
    )

    await service.complete(_request("What is photosynthesis?"))
    await service.complete(_request("What is the Krebs cycle?"))

    assert provider.calls[0][0].content == BASE_SYSTEM_PROMPT
    assert provider.calls[1][0].content == BASE_SYSTEM_PROMPT
    assert provider.calls[0][-1].content != provider.calls[1][-1].content


@pytest.mark.asyncio
async def test_llm_service_complete_starts_retrieval_before_input_guardrail_finishes() -> None:
    provider = FakeProvider()
    retriever = CoordinatedRetriever()
    service = LLMService(
        provider=provider,
        guardrails=WaitForRetrievalGuardrails(retriever.started),
        retriever=retriever,
    )

    result = await service.complete(_request("What is concurrent retrieval?"))

    assert result.retrieved_context[0].metadata["source_id"] == "doc_concurrent"
    assert provider.complete_called
    assert "Concurrent note for: What is concurrent retrieval?" in provider.messages[-1].content
    assert provider.messages[0].content == BASE_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_llm_service_complete_ignores_retrieval_when_input_is_blocked() -> None:
    provider = FakeProvider()
    retriever = ReleasableRetriever()
    service = LLMService(
        provider=provider,
        guardrails=WaitForRetrievalGuardrails(retriever.started, blocked=True),
        retriever=retriever,
    )

    result = await service.complete(_request("bad input"))
    await asyncio.sleep(0)

    assert result.input_guardrail_result.blocked
    assert result.content == "Input blocked."
    assert not provider.complete_called
    assert result.retrieved_context == []
    await asyncio.wait_for(retriever.cancelled.wait(), timeout=1)


@pytest.mark.asyncio
async def test_llm_service_consumes_ignored_retrieval_exception() -> None:
    loop = asyncio.get_running_loop()
    captured_contexts = []
    previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(
        lambda loop, context: captured_contexts.append(context),
    )

    try:
        retriever = FailingRetriever()
        service = LLMService(
            provider=FakeProvider(),
            guardrails=WaitForRetrievalDoneGuardrails(retriever.done),
            retriever=retriever,
        )

        result = await service.complete(_request("bad input"))
        await asyncio.sleep(0)

        assert result.input_guardrail_result.blocked
        assert captured_contexts == []
    finally:
        loop.set_exception_handler(previous_handler)


@pytest.mark.asyncio
async def test_llm_service_degrades_allowed_retrieval_failure_to_empty_context(
    caplog,
) -> None:
    caplog.set_level(logging.INFO, logger="backend.llm.service")
    provider = FakeProvider()
    trace_sink = RecordingTraceSink()
    service = LLMService(
        provider=provider,
        guardrails=AllowGuardrails(),
        retriever=FailingRetriever(),
        trace_sink=trace_sink,
    )

    result = await service.complete(_request("What is photosynthesis?"))

    assert result.content == "Plants turn light into energy."
    assert result.retrieved_context == []
    assert provider.complete_called
    assert "<retrieved_context>" not in provider.messages[-1].content
    failed_events = _events(caplog.records, "rag.retrieve.failed")
    assert failed_events[-1].error_type == "RuntimeError"
    assert failed_events[-1].retriever_class == "FailingRetriever"
    assert _events(caplog.records, "rag.retrieve.completed") == []
    assert trace_sink.errors[-1]["error_type"] == "RuntimeError"
    assert trace_sink.errors[-1]["retriever_class"] == "FailingRetriever"
