import asyncio
from uuid import UUID, uuid4

import pytest

from backend.llm.config import llm_settings
from backend.llm.provider import LiteLLMProvider
from backend.llm.schemas import (
    ChatMessage,
    ChatRole,
    GuardrailResult,
    LLMBlocked,
    LLMDelta,
    LLMRequest,
    LLMResult,
    ProviderResponse,
    ProviderStreamChunk,
    RetrievedChunk,
)
from backend.llm.service import LLMService


class FakeProvider:
    def __init__(self) -> None:
        self.messages: list[ChatMessage] = []
        self.stream_messages: list[ChatMessage] = []
        self.complete_called = False
        self.stream_called = False

    async def complete(self, messages: list[ChatMessage]) -> ProviderResponse:
        self.complete_called = True
        self.messages = messages
        return ProviderResponse(
            content="Plants turn light into energy.", finish_reason="stop"
        )

    async def stream(self, messages: list[ChatMessage]):
        self.stream_called = True
        self.stream_messages = messages
        yield ProviderStreamChunk(text="Plants ", model="provider/model")
        yield ProviderStreamChunk(text="stream.", finish_reason="stop")


class FakeRetriever:
    async def retrieve(self, query: str, *, user_id: UUID, conversation_id: UUID):
        return [
            RetrievedChunk(
                content=f"Relevant note for: {query}",
                source_id="doc_1",
                title="Biology Notes",
                page=3,
            ),
        ]


class CoordinatedRetriever:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def retrieve(self, query: str, *, user_id: UUID, conversation_id: UUID):
        self.started.set()
        return [
            RetrievedChunk(
                content=f"Concurrent note for: {query}",
                source_id="doc_concurrent",
                title="Concurrent Notes",
            ),
        ]


class ReleasableRetriever:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def retrieve(self, query: str, *, user_id: UUID, conversation_id: UUID):
        self.started.set()
        await self.release.wait()
        if self.fail:
            raise RuntimeError("ignored retrieval failure")
        return [
            RetrievedChunk(
                content=f"Ignored note for: {query}",
                source_id="doc_ignored",
                title="Ignored Notes",
            ),
        ]


class AllowGuardrails:
    has_output_guardrail = True

    async def check_input(self, content: str) -> GuardrailResult:
        return GuardrailResult(metadata={"input": content})

    async def check_output(self, content: str, *, user_input: str) -> GuardrailResult:
        return GuardrailResult(metadata={"output": content, "userInput": user_input})


class BlockingInputGuardrails(AllowGuardrails):
    async def check_input(self, content: str) -> GuardrailResult:
        return GuardrailResult(blocked=True, reason="Input blocked.", rail="input")


class WaitForRetrievalGuardrails(AllowGuardrails):
    def __init__(self, started: asyncio.Event, *, blocked: bool = False) -> None:
        self._started = started
        self._blocked = blocked

    async def check_input(self, content: str) -> GuardrailResult:
        await self._started.wait()
        if self._blocked:
            return GuardrailResult(blocked=True, reason="Input blocked.", rail="input")
        return await super().check_input(content)


class BlockingOutputGuardrails(AllowGuardrails):
    async def check_output(self, content: str, *, user_input: str) -> GuardrailResult:
        return GuardrailResult(blocked=True, reason="Output blocked.", rail="output")


class NoOutputGuardrails(AllowGuardrails):
    has_output_guardrail = False

    async def check_output(self, content: str, *, user_input: str) -> GuardrailResult:
        raise AssertionError("output guardrail should not run while streaming")


@pytest.mark.asyncio
async def test_llm_service_adds_retrieved_context_to_system_prompt() -> None:
    provider = FakeProvider()
    service = LLMService(
        provider=provider,
        guardrails=AllowGuardrails(),
        retriever=FakeRetriever(),
    )

    result = await service.complete(_request("What is photosynthesis?"))

    assert result.content == "Plants turn light into energy."
    assert result.citations[0].source_id == "doc_1"
    assert provider.messages[0].role == ChatRole.SYSTEM
    assert "Relevant note for: What is photosynthesis?" in provider.messages[0].content


@pytest.mark.asyncio
async def test_llm_service_complete_starts_retrieval_before_input_guardrail_finishes() -> (
    None
):
    provider = FakeProvider()
    retriever = CoordinatedRetriever()
    service = LLMService(
        provider=provider,
        guardrails=WaitForRetrievalGuardrails(retriever.started),
        retriever=retriever,
    )

    result = await service.complete(_request("What is concurrent retrieval?"))

    assert result.citations[0].source_id == "doc_concurrent"
    assert provider.complete_called
    assert (
        "Concurrent note for: What is concurrent retrieval?"
        in provider.messages[0].content
    )


@pytest.mark.asyncio
async def test_llm_service_blocks_unsafe_input_before_provider_call() -> None:
    provider = FakeProvider()
    service = LLMService(
        provider=provider,
        guardrails=BlockingInputGuardrails(),
        retriever=FakeRetriever(),
    )

    events = [event async for event in service.stream(_request("bad input"))]

    assert isinstance(events[0], LLMBlocked)
    assert events[0].reason == "Input blocked."
    assert provider.messages == []
    assert not provider.complete_called
    assert not provider.stream_called


@pytest.mark.asyncio
async def test_llm_service_stream_ignores_retrieval_when_input_is_blocked() -> None:
    provider = FakeProvider()
    retriever = ReleasableRetriever()
    service = LLMService(
        provider=provider,
        guardrails=WaitForRetrievalGuardrails(retriever.started, blocked=True),
        retriever=retriever,
    )

    events = [event async for event in service.stream(_request("bad input"))]
    retriever.release.set()
    await asyncio.sleep(0)

    assert isinstance(events[0], LLMBlocked)
    assert events[0].reason == "Input blocked."
    assert not provider.complete_called
    assert not provider.stream_called


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
    retriever.release.set()
    await asyncio.sleep(0)

    assert result.content == "Input blocked."
    assert result.citations == []
    assert result.retrieved_context == []
    assert not provider.complete_called
    assert not provider.stream_called


@pytest.mark.asyncio
async def test_llm_service_consumes_ignored_retrieval_exception() -> None:
    loop = asyncio.get_running_loop()
    captured_contexts = []
    previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(
        lambda loop, context: captured_contexts.append(context),
    )

    try:
        retriever = ReleasableRetriever(fail=True)
        service = LLMService(
            provider=FakeProvider(),
            guardrails=WaitForRetrievalGuardrails(retriever.started, blocked=True),
            retriever=retriever,
        )

        events = [event async for event in service.stream(_request("bad input"))]
        retriever.release.set()
        await asyncio.sleep(0)

        assert isinstance(events[0], LLMBlocked)
        assert captured_contexts == []
    finally:
        loop.set_exception_handler(previous_handler)


@pytest.mark.asyncio
async def test_llm_service_streams_provider_chunks_without_output_guardrail() -> None:
    provider = FakeProvider()
    service = LLMService(
        provider=provider,
        guardrails=NoOutputGuardrails(),
        retriever=FakeRetriever(),
    )

    events = [event async for event in service.stream(_request("stream this"))]

    assert [event.text for event in events if isinstance(event, LLMDelta)] == [
        "Plants ",
        "stream.",
    ]
    assert isinstance(events[-1], LLMResult)
    assert events[-1].content == "Plants stream."
    assert events[-1].provider_response is not None
    assert events[-1].provider_response.finish_reason == "stop"
    assert provider.stream_called
    assert not provider.complete_called
    assert provider.stream_messages[0].role == ChatRole.SYSTEM


@pytest.mark.asyncio
async def test_llm_service_blocks_unsafe_output_before_delta_events() -> None:
    service = LLMService(
        provider=FakeProvider(),
        guardrails=BlockingOutputGuardrails(),
        retriever=FakeRetriever(),
    )

    events = [event async for event in service.stream(_request("safe input"))]

    assert isinstance(events[0], LLMBlocked)
    assert not any(isinstance(event, LLMDelta) for event in events)


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
    assert "api_key" not in captured_kwargs


@pytest.mark.asyncio
async def test_litellm_provider_streams_configured_model_chunks(monkeypatch) -> None:
    captured_kwargs = {}

    async def fake_acompletion(**kwargs):
        captured_kwargs.update(kwargs)
        return _FakeLiteLLMStream(
            [
                _FakeLiteLLMStreamChunk("Configured ", None),
                _FakeLiteLLMStreamChunk("stream.", "stop"),
            ],
        )

    monkeypatch.setattr("backend.llm.provider.acompletion", fake_acompletion)

    provider = LiteLLMProvider()
    chunks = [
        chunk
        async for chunk in provider.stream(
            [ChatMessage(role=ChatRole.USER, content="hello")]
        )
    ]

    assert [chunk.text for chunk in chunks] == ["Configured ", "stream."]
    assert chunks[-1].finish_reason == "stop"
    assert captured_kwargs["model"] == llm_settings.model
    assert captured_kwargs["stream"] is True


def _request(content: str) -> LLMRequest:
    return LLMRequest(
        user_id=uuid4(),
        conversation_id=uuid4(),
        message_id=uuid4(),
        content=content,
    )


class _FakeLiteLLMUsage:
    prompt_tokens = 3
    completion_tokens = 4
    total_tokens = 7


class _FakeLiteLLMMessage:
    content = "Configured model response."


class _FakeLiteLLMChoice:
    message = _FakeLiteLLMMessage()
    finish_reason = "stop"


class _FakeLiteLLMResponse:
    choices = [_FakeLiteLLMChoice()]
    usage = _FakeLiteLLMUsage()
    model = "provider/model"

    def model_dump(self, mode: str):
        return {"model": self.model, "mode": mode}


class _FakeLiteLLMDelta:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLiteLLMStreamChoice:
    def __init__(self, content: str, finish_reason: str | None) -> None:
        self.delta = _FakeLiteLLMDelta(content)
        self.finish_reason = finish_reason


class _FakeLiteLLMStreamChunk:
    model = "provider/model"
    usage = None

    def __init__(self, content: str, finish_reason: str | None) -> None:
        self.choices = [_FakeLiteLLMStreamChoice(content, finish_reason)]

    def model_dump(self, mode: str):
        return {"model": self.model, "mode": mode}


class _FakeLiteLLMStream:
    def __init__(self, chunks: list[_FakeLiteLLMStreamChunk]) -> None:
        self._chunks = chunks

    def __aiter__(self):
        return self._stream()

    async def _stream(self):
        for chunk in self._chunks:
            yield chunk
