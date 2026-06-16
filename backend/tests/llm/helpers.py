import asyncio
import json
from uuid import UUID, uuid4

from backend.core.observability import LLMTraceOperation, LLMTraceSink, NoopLLMTraceSink
from backend.llm.schemas import ChatMessage, GuardrailResult, LLMRequest, ProviderResponse
from backend.rag.schemas import RagRetrievalLogRecord, RetrievalResult, RetrievedChunk


class FakeProvider:
    def __init__(self) -> None:
        self.messages: list[ChatMessage] = []
        self.calls: list[list[ChatMessage]] = []
        self.complete_called = False

    async def complete(self, messages: list[ChatMessage]) -> ProviderResponse:
        self.complete_called = True
        self.messages = messages
        self.calls.append(messages)
        return ProviderResponse(content="Plants turn light into energy.", finish_reason="stop")


class SequenceProvider:
    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.calls: list[list[ChatMessage]] = []

    async def complete(self, messages: list[ChatMessage]) -> ProviderResponse:
        self.calls.append(messages)
        return ProviderResponse(
            content=self._responses[len(self.calls) - 1],
            finish_reason="stop",
        )


class FakeRetriever:
    async def retrieve(
        self,
        query: str,
        *,
        user_id: UUID,
        conversation_id: UUID,
        user_message_id: UUID,
    ):
        return RetrievalResult(
            chunks=[
                RetrievedChunk(
                    content=f"Relevant note for: {query}",
                    metadata={
                        "source_id": "doc_1",
                        "title": "Biology Notes",
                        "page": 3,
                    },
                ),
            ],
        )


class RichChunkRetriever:
    async def retrieve(
        self,
        query: str,
        *,
        user_id: UUID,
        conversation_id: UUID,
        user_message_id: UUID,
    ):
        return RetrievalResult(
            chunks=[
                RetrievedChunk(
                    content=f"Rich note for: {query}",
                    metadata={
                        "source_id": "doc_1",
                        "title": "Biology Notes",
                    },
                    distance=0.12,
                )
            ],
        )


class CoordinatedRetriever:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def retrieve(
        self,
        query: str,
        *,
        user_id: UUID,
        conversation_id: UUID,
        user_message_id: UUID,
    ):
        self.started.set()
        return RetrievalResult(
            chunks=[
                RetrievedChunk(
                    content=f"Concurrent note for: {query}",
                    metadata={
                        "source_id": "doc_concurrent",
                        "title": "Concurrent Notes",
                    },
                ),
            ],
        )


class ReleasableRetriever:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def retrieve(
        self,
        query: str,
        *,
        user_id: UUID,
        conversation_id: UUID,
        user_message_id: UUID,
    ):
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        if self.fail:
            raise RuntimeError("ignored retrieval failure")
        return RetrievalResult(
            chunks=[
                RetrievedChunk(
                    content=f"Ignored note for: {query}",
                    metadata={
                        "source_id": "doc_ignored",
                        "title": "Ignored Notes",
                    },
                ),
            ],
        )


class FailingRetriever:
    def __init__(self) -> None:
        self.done = asyncio.Event()

    async def retrieve(
        self,
        query: str,
        *,
        user_id: UUID,
        conversation_id: UUID,
        user_message_id: UUID,
    ):
        try:
            raise RuntimeError("ignored retrieval failure")
        finally:
            self.done.set()


class AllowGuardrails:
    async def check_input(self, content: str) -> GuardrailResult:
        return GuardrailResult(metadata={"input": content})

    async def check_output(self, content: str, *, user_input: str) -> GuardrailResult:
        return GuardrailResult(metadata={"output": content, "userInput": user_input})


class BlockingInputGuardrails(AllowGuardrails):
    async def check_input(self, content: str) -> GuardrailResult:
        return GuardrailResult(blocked=True, reason="Input blocked.", rail="input")


class FailingInputGuardrails(AllowGuardrails):
    async def check_input(self, content: str) -> GuardrailResult:
        raise RuntimeError("guardrail unavailable")


class WaitForRetrievalGuardrails(AllowGuardrails):
    def __init__(self, started: asyncio.Event, *, blocked: bool = False) -> None:
        self._started = started
        self._blocked = blocked

    async def check_input(self, content: str) -> GuardrailResult:
        await self._started.wait()
        if self._blocked:
            return GuardrailResult(blocked=True, reason="Input blocked.", rail="input")
        return await super().check_input(content)


class WaitForRetrievalDoneGuardrails(AllowGuardrails):
    def __init__(self, done: asyncio.Event) -> None:
        self._done = done

    async def check_input(self, content: str) -> GuardrailResult:
        await self._done.wait()
        return GuardrailResult(blocked=True, reason="Input blocked.", rail="input")


class BlockingOutputGuardrails(AllowGuardrails):
    async def check_output(self, content: str, *, user_input: str) -> GuardrailResult:
        return GuardrailResult(blocked=True, reason="Output blocked.", rail="output")


class RepairableOutputGuardrails(AllowGuardrails):
    async def check_output(self, content: str, *, user_input: str) -> GuardrailResult:
        if "direct answer" in content:
            return GuardrailResult(
                blocked=True,
                reason="Output blocked.",
                rail="output",
                metadata={"draft": content},
            )
        return await super().check_output(content, user_input=user_input)


def _events(records, event: str):
    return [record for record in records if getattr(record, "event", None) == event]


class FailingTraceSink(NoopLLMTraceSink):
    async def record(self, operation, metadata):
        raise RuntimeError("trace sink unavailable")


class IncompleteTraceSink(LLMTraceSink):
    pass


class RecordingTraceSink(NoopLLMTraceSink):
    def __init__(self) -> None:
        self.errors = []
        self.generations = []
        self.repairs = []

    async def record(self, operation, metadata):
        if operation == LLMTraceOperation.RECORD_GENERATION:
            self.generations.append(metadata)
        if operation == LLMTraceOperation.RECORD_REPAIR:
            self.repairs.append(metadata)
        if operation == LLMTraceOperation.RECORD_ERROR:
            self.errors.append(metadata)


class RecordingRetrievalTraceSink:
    def __init__(self) -> None:
        self.records: list[RagRetrievalLogRecord] = []

    async def record_retrieval(self, record: RagRetrievalLogRecord) -> None:
        self.records.append(record)


class FailingRetrievalTraceSink:
    async def record_retrieval(self, record: RagRetrievalLogRecord) -> None:
        raise RuntimeError("retrieval trace sink unavailable")


def _request(content: str) -> LLMRequest:
    return LLMRequest(
        user_id=uuid4(),
        conversation_id=uuid4(),
        user_message_id=uuid4(),
        assistant_message_id=uuid4(),
        content=content,
    )


def _judge_response(
    *,
    blocked: bool,
    rail: str,
    reason: str | None = None,
) -> dict:
    return {
        "model": "gpt-4o-mini",
        "usage": {
            "prompt_tokens": 3,
            "completion_tokens": 1,
            "total_tokens": 4,
        },
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "content": json.dumps(
                        {
                            "blocked": blocked,
                            "reason": reason,
                            "rail": rail,
                            "confidence": 0.8,
                        }
                    )
                },
            }
        ],
    }


class _FakeLiteLLMUsage:
    prompt_tokens = 3
    completion_tokens = 4
    total_tokens = 7


class _FakeLiteLLMMessage:
    def __init__(self, content: str = "Configured model response.") -> None:
        self.content = content


class _FakeLiteLLMChoice:
    def __init__(self, content: str = "Configured model response.") -> None:
        self.message = _FakeLiteLLMMessage(content)
        self.finish_reason = "stop"


class _FakeLiteLLMResponse:
    usage = _FakeLiteLLMUsage()

    def __init__(self, content: str = "Configured model response.") -> None:
        self.choices = [_FakeLiteLLMChoice(content)]
        self.model = "provider/model"

    def model_dump(self, mode: str):
        return {"model": self.model, "mode": mode}


class _FakeEmptyLiteLLMResponse:
    choices = []
