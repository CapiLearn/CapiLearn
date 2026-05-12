import asyncio
from uuid import UUID, uuid4

import pytest

from backend.llm.config import llm_settings
from backend.llm.provider import LiteLLMProvider
from backend.llm.schemas import (
    ChatMessage,
    ChatRole,
    GuardrailResult,
    LLMRequest,
    ProviderResponse,
    RetrievedChunk,
)
from backend.llm.service import LLMService


class FakeProvider:
    def __init__(self) -> None:
        self.messages: list[ChatMessage] = []
        self.complete_called = False

    async def complete(self, messages: list[ChatMessage]) -> ProviderResponse:
        self.complete_called = True
        self.messages = messages
        return ProviderResponse(
            content="Plants turn light into energy.", finish_reason="stop"
        )


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
    assert result.retrieved_context[0].source_id == "doc_1"
    assert "citations" not in result.model_dump()
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

    assert result.retrieved_context[0].source_id == "doc_concurrent"
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

    result = await service.complete(_request("bad input"))

    assert result.input_guardrail_result.blocked
    assert result.content == "Input blocked."
    assert provider.messages == []
    assert not provider.complete_called


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

    assert result.input_guardrail_result.blocked
    assert result.content == "Input blocked."
    assert not provider.complete_called
    assert result.retrieved_context == []


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

        result = await service.complete(_request("bad input"))
        retriever.release.set()
        await asyncio.sleep(0)

        assert result.input_guardrail_result.blocked
        assert captured_contexts == []
    finally:
        loop.set_exception_handler(previous_handler)


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
