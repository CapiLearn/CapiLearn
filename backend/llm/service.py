import asyncio
import logging

from backend.core.observability import (
    LLMTraceSink,
    NoopLLMTraceSink,
    elapsed_ms,
    log_event,
    timer_start,
)
from backend.llm.config import InputGuardrailMode, OutputGuardrailMode, llm_settings
from backend.llm.guardrails import (
    CompositeGuardrailsProvider,
    LLMJudgeGuardrailsProvider,
    NoopGuardrailsProvider,
    RegexGuardrailsProvider,
)
from backend.llm.prompts import build_messages, build_socratic_repair_messages
from backend.llm.provider import LiteLLMProvider
from backend.llm.schemas import (
    ChatMessage,
    GuardrailResult,
    GuardrailsProvider,
    LLMProvider,
    LLMRequest,
    LLMResult,
    ProviderResponse,
    RetrievalProvider,
    RetrievalResult,
    RetrievedChunk,
)

logger = logging.getLogger(__name__)


class EmptyRetrievalProvider:
    async def retrieve(
        self,
        query: str,
        *,
        user_id,
        conversation_id,
        user_message_id,
    ) -> RetrievalResult:
        return RetrievalResult(chunks=[])


class LLMService:
    def __init__(
        self,
        *,
        provider: LLMProvider | None = None,
        guardrails: GuardrailsProvider | None = None,
        input_guardrails: GuardrailsProvider | None = None,
        output_guardrails: GuardrailsProvider | None = None,
        retriever: RetrievalProvider | None = None,
        trace_sink: LLMTraceSink | None = None,
    ) -> None:
        self._provider = provider or LiteLLMProvider()
        self._input_guardrails = guardrails or input_guardrails or _build_input_guardrails()
        self._output_guardrails = guardrails or output_guardrails or _build_output_guardrails()
        self._retriever = retriever or EmptyRetrievalProvider()
        self._trace_sink = trace_sink or NoopLLMTraceSink()

    async def complete(self, request: LLMRequest) -> LLMResult:
        retrieval_started_at = timer_start()
        retrieval_task = asyncio.create_task(
            self._retriever.retrieve(
                request.content,
                user_id=request.user_id,
                conversation_id=request.conversation_id,
                user_message_id=request.user_message_id,
            ),
        )

        input_guardrail_started_at = timer_start()
        try:
            input_result = await self._input_guardrails.check_input(request.content)
        except asyncio.CancelledError:
            _discard_task_result(retrieval_task)
            raise
        except Exception as exc:
            _discard_task_result(retrieval_task)
            await self._record_guardrail_error(
                request=request,
                stage="input",
                started_at=input_guardrail_started_at,
                exc=exc,
            )
            raise
        await self._record_guardrail_result(
            request=request,
            stage="input",
            started_at=input_guardrail_started_at,
            result=input_result,
        )

        if input_result.blocked:
            _discard_task_result(retrieval_task)
            provider_response = ProviderResponse(content="")
            output_result = GuardrailResult()
            return _build_result(
                input_result=input_result,
                output_result=output_result,
                provider_response=provider_response,
                retrieval_result=RetrievalResult(chunks=[]),
            )

        try:
            retrieval_result = _coerce_retrieval_result(await retrieval_task)
        except Exception as exc:
            latency_ms = elapsed_ms(retrieval_started_at)
            fields = {
                **_request_event_fields(request),
                "latency_ms": latency_ms,
                "error_type": type(exc).__name__,
            }
            await self._trace_sink.record_error(fields)
            log_event(logger, "rag.retrieve.failed", level=logging.ERROR, **fields)
            raise
        await self._record_retrieval_result(
            request=request,
            started_at=retrieval_started_at,
            result=retrieval_result,
        )

        provider_response = await self._generate(
            request=request,
            messages=build_messages(
                user_input=request.content,
                history=request.history,
                chunks=retrieval_result.chunks,
            ),
            stage="primary",
        )
        output_result, provider_response = await self._check_output(
            request=request,
            provider_response=provider_response,
            retrieved_context=retrieval_result.chunks,
        )
        return _build_result(
            input_result=input_result,
            output_result=output_result,
            provider_response=provider_response,
            retrieval_result=retrieval_result,
        )

    async def _check_output(
        self,
        *,
        request: LLMRequest,
        provider_response: ProviderResponse,
        retrieved_context: list[RetrievedChunk],
    ) -> tuple[GuardrailResult, ProviderResponse]:
        output_guardrail_started_at = timer_start()
        try:
            output_result = await self._output_guardrails.check_output(
                provider_response.content,
                user_input=request.content,
            )
        except Exception as exc:
            await self._record_guardrail_error(
                request=request,
                stage="output",
                started_at=output_guardrail_started_at,
                exc=exc,
            )
            raise
        await self._record_guardrail_result(
            request=request,
            stage="output",
            started_at=output_guardrail_started_at,
            result=output_result,
        )
        if not output_result.blocked:
            return output_result, provider_response

        repair_started_at = timer_start()
        repair_response = await self._generate(
            request=request,
            messages=build_socratic_repair_messages(
                user_input=request.content,
                draft_response=provider_response.content,
                chunks=retrieved_context,
            ),
            stage="repair",
        )
        repair_guardrail_started_at = timer_start()
        try:
            repair_result = await self._output_guardrails.check_output(
                repair_response.content,
                user_input=request.content,
            )
        except Exception as exc:
            await self._record_guardrail_error(
                request=request,
                stage="output_repair",
                started_at=repair_guardrail_started_at,
                exc=exc,
            )
            raise
        await self._record_guardrail_result(
            request=request,
            stage="output_repair",
            started_at=repair_guardrail_started_at,
            result=repair_result,
        )
        repair_fields = {
            **_request_event_fields(request),
            "latency_ms": elapsed_ms(repair_started_at),
            "repair_passed": not repair_result.blocked,
            "initial_blocked": output_result.blocked,
            "initial_rail": output_result.rail,
            "final_rail": repair_result.rail,
        }
        await self._trace_sink.record_generation(repair_fields)
        log_event(logger, "chat.repair.completed", **repair_fields)
        return (
            _with_repair_metadata(repair_result, initial_result=output_result),
            repair_response,
        )

    async def _generate(
        self,
        *,
        request: LLMRequest,
        messages: list[ChatMessage],
        stage: str,
    ) -> ProviderResponse:
        started_at = timer_start()
        try:
            provider_response = await self._provider.complete(messages)
        except Exception as exc:
            fields = {
                **_request_event_fields(request),
                "generation_stage": stage,
                "latency_ms": elapsed_ms(started_at),
                "error_type": type(exc).__name__,
            }
            await self._trace_sink.record_error(fields)
            log_event(logger, "llm.generation.failed", level=logging.ERROR, **fields)
            raise

        measured_latency_ms = elapsed_ms(started_at)
        if provider_response.latency_ms is None:
            provider_response.latency_ms = measured_latency_ms
        fields = {
            **_request_event_fields(request),
            "generation_stage": stage,
            "model": provider_response.model,
            "finish_reason": provider_response.finish_reason,
            "prompt_tokens": provider_response.prompt_tokens,
            "completion_tokens": provider_response.completion_tokens,
            "total_tokens": provider_response.total_tokens,
            "latency_ms": provider_response.latency_ms,
        }
        await self._trace_sink.record_generation(fields)
        log_event(logger, "llm.generation.completed", **fields)
        return provider_response

    async def _record_guardrail_result(
        self,
        *,
        request: LLMRequest,
        stage: str,
        started_at: float,
        result: GuardrailResult,
    ) -> None:
        fields = {
            **_request_event_fields(request),
            **_guardrail_event_fields(result),
            "guardrail_stage": stage,
            "latency_ms": elapsed_ms(started_at),
        }
        await self._trace_sink.record_guardrail(fields)
        log_event(logger, "guardrail.check.completed", **fields)

    async def _record_guardrail_error(
        self,
        *,
        request: LLMRequest,
        stage: str,
        started_at: float,
        exc: Exception,
    ) -> None:
        fields = {
            **_request_event_fields(request),
            "guardrail_stage": stage,
            "latency_ms": elapsed_ms(started_at),
            "error_type": type(exc).__name__,
        }
        await self._trace_sink.record_error(fields)
        log_event(logger, "guardrail.check.failed", level=logging.ERROR, **fields)

    async def _record_retrieval_result(
        self,
        *,
        request: LLMRequest,
        started_at: float,
        result: RetrievalResult,
    ) -> None:
        fields = {
            **_request_event_fields(request),
            "latency_ms": elapsed_ms(started_at),
            "chunk_count": len(result.chunks),
            "chunks": [_chunk_observability_metadata(chunk) for chunk in result.chunks[:5]],
        }
        await self._trace_sink.record_retrieval(fields)
        log_event(logger, "rag.retrieve.completed", **fields)


def _build_input_guardrails() -> GuardrailsProvider:
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


def _build_output_guardrails() -> GuardrailsProvider:
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


def _build_result(
    *,
    input_result: GuardrailResult,
    output_result: GuardrailResult,
    provider_response: ProviderResponse,
    retrieval_result: RetrievalResult,
) -> LLMResult:
    content = provider_response.content
    if input_result.blocked:
        content = input_result.reason or "That request was blocked by guardrails."
    elif output_result.blocked:
        content = output_result.reason or "That response was blocked by guardrails."

    return LLMResult(
        content=content,
        retrieval_result=retrieval_result,
        retrieved_context=retrieval_result.chunks,
        input_guardrail_result=input_result,
        output_guardrail_result=output_result,
        provider_response=provider_response,
    )


def _with_repair_metadata(
    result: GuardrailResult,
    *,
    initial_result: GuardrailResult,
) -> GuardrailResult:
    metadata = dict(result.metadata)
    metadata["repairAttempted"] = True
    metadata["repairPassed"] = not result.blocked
    metadata["initialOutputGuardrailResult"] = initial_result.model_dump(
        mode="json",
        by_alias=True,
    )
    return result.model_copy(update={"metadata": metadata})


def _coerce_retrieval_result(
    value: RetrievalResult | list[RetrievedChunk | dict],
) -> RetrievalResult:
    if isinstance(value, RetrievalResult):
        return value
    return RetrievalResult(chunks=[_coerce_retrieved_chunk(chunk) for chunk in value])


def _coerce_retrieved_chunk(value: RetrievedChunk | dict) -> RetrievedChunk:
    if isinstance(value, RetrievedChunk):
        return value
    return RetrievedChunk.model_validate(value)


def _request_event_fields(request: LLMRequest) -> dict:
    return {
        "user_id": str(request.user_id),
        "conversation_id": str(request.conversation_id),
        "user_message_id": str(request.user_message_id),
        "assistant_message_id": (
            str(request.assistant_message_id) if request.assistant_message_id else None
        ),
    }


def _guardrail_event_fields(result: GuardrailResult) -> dict:
    metadata = result.metadata or {}
    return {
        "blocked": result.blocked,
        "rail": result.rail,
        "reason": _reason_code(result.reason),
        "guardrail_provider": metadata.get("provider"),
        "category": metadata.get("category"),
        "confidence": metadata.get("confidence"),
        "fail_open": metadata.get("failOpen"),
        "judge_error": metadata.get("judgeError"),
    }


def _reason_code(reason: str | None) -> str | None:
    if reason is None:
        return None
    return "_".join(reason.lower().split())[:80]


def _chunk_observability_metadata(chunk: RetrievedChunk) -> dict:
    metadata = chunk.metadata or {}
    allowed_keys = {
        "source_id",
        "sourceId",
        "chunk_id",
        "chunkId",
        "document_id",
        "documentId",
        "title",
        "source_path",
        "sourcePath",
        "page",
        "score",
        "distance",
    }
    return {key: metadata[key] for key in allowed_keys if key in metadata}


def _discard_task_result(task: asyncio.Task[RetrievalResult]) -> None:
    task.cancel()
    task.add_done_callback(_consume_task_exception)


def _consume_task_exception(task: asyncio.Task[RetrievalResult]) -> None:
    try:
        task.exception()
    except asyncio.CancelledError:
        pass
