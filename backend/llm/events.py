import logging
from typing import Any

from backend.core.observability import LLMTraceOperation, LLMTraceSink, elapsed_ms, log_event
from backend.llm.schemas import GuardrailResult, LLMRequest, ProviderResponse
from backend.rag.schemas import (
    RetrievalResult,
    build_rag_retrieval_log_record,
    retrieval_chunk_log_metadata,
)
from backend.rag.trace_contracts import RetrievalTraceSink


class LLMEventRecorder:
    def __init__(
        self,
        *,
        trace_sink: LLMTraceSink,
        retrieval_trace_sink: RetrievalTraceSink,
        logger: logging.Logger,
        request: LLMRequest,
    ) -> None:
        self._trace_sink = trace_sink
        self._retrieval_trace_sink = retrieval_trace_sink
        self._logger = logger
        self._request_fields = request_event_fields(request)
        self._query_text = request.content

    async def record_guardrail_result(
        self,
        *,
        stage: str,
        started_at: float,
        result: GuardrailResult,
    ) -> None:
        fields = {
            **self._request_fields,
            **guardrail_event_fields(result),
            "guardrail_stage": stage,
            "latency_ms": elapsed_ms(started_at),
        }
        await self._trace_sink.record(LLMTraceOperation.RECORD_GUARDRAIL, fields)
        log_event(self._logger, "guardrail.check.completed", **fields)

    async def record_guardrail_error(
        self,
        *,
        stage: str,
        started_at: float,
        exc: Exception,
    ) -> None:
        fields = {
            **self._request_fields,
            "guardrail_stage": stage,
            "latency_ms": elapsed_ms(started_at),
            "error_type": type(exc).__name__,
        }
        await self._trace_sink.record(LLMTraceOperation.RECORD_ERROR, fields)
        log_event(
            self._logger,
            "guardrail.check.failed",
            level=logging.ERROR,
            **fields,
            exc_info=exc,
        )

    async def record_retrieval_result(
        self,
        *,
        started_at: float,
        result: RetrievalResult,
    ) -> None:
        chunks = [retrieval_chunk_log_metadata(chunk) for chunk in result.chunks]
        fields = {
            **self._request_fields,
            "latency_ms": elapsed_ms(started_at),
            "chunk_count": len(result.chunks),
            "chunks": chunks,
        }
        await self._retrieval_trace_sink.record_retrieval(
            build_rag_retrieval_log_record(
                query_text=self._query_text,
                result=result,
                conversation_id=self._request_fields["conversation_id"],
                user_message_id=self._request_fields["user_message_id"],
            )
        )
        log_event(
            self._logger,
            "rag.retrieve.completed",
            **{**fields, "chunks": chunks[:5]},
        )

    async def record_retrieval_error(
        self,
        *,
        started_at: float,
        exc: Exception,
        retriever_class: str,
    ) -> None:
        fields = {
            **self._request_fields,
            "latency_ms": elapsed_ms(started_at),
            "error_type": type(exc).__name__,
            "retriever_class": retriever_class,
        }
        await self._trace_sink.record(LLMTraceOperation.RECORD_ERROR, fields)
        log_event(
            self._logger,
            "rag.retrieve.failed",
            level=logging.WARNING,
            **fields,
        )

    async def record_generation_error(
        self,
        *,
        stage: str,
        started_at: float,
        exc: Exception,
    ) -> None:
        fields = {
            **self._request_fields,
            "generation_stage": stage,
            "latency_ms": elapsed_ms(started_at),
            "error_type": type(exc).__name__,
        }
        await self._trace_sink.record(LLMTraceOperation.RECORD_ERROR, fields)
        log_event(
            self._logger,
            "llm.generation.failed",
            level=logging.ERROR,
            **fields,
            exc_info=exc,
        )

    async def record_generation_result(
        self,
        *,
        stage: str,
        provider_response: ProviderResponse,
    ) -> None:
        fields = {
            **self._request_fields,
            "generation_stage": stage,
            "model": provider_response.model,
            "finish_reason": provider_response.finish_reason,
            "prompt_tokens": provider_response.prompt_tokens,
            "completion_tokens": provider_response.completion_tokens,
            "total_tokens": provider_response.total_tokens,
            "latency_ms": provider_response.latency_ms,
        }
        await self._trace_sink.record(LLMTraceOperation.RECORD_GENERATION, fields)
        log_event(self._logger, "llm.generation.completed", **fields)

    async def record_repair_completed(
        self,
        *,
        started_at: float,
        repair_result: GuardrailResult,
        initial_result: GuardrailResult,
    ) -> None:
        fields = {
            **self._request_fields,
            "latency_ms": elapsed_ms(started_at),
            "repair_passed": not repair_result.blocked,
            "initial_blocked": initial_result.blocked,
            "initial_rail": initial_result.rail,
            "final_rail": repair_result.rail,
        }
        await self._trace_sink.record(LLMTraceOperation.RECORD_REPAIR, fields)
        log_event(self._logger, "chat.repair.completed", **fields)


def request_event_fields(request: LLMRequest) -> dict[str, Any]:
    return {
        "user_id": str(request.user_id),
        "conversation_id": str(request.conversation_id),
        "user_message_id": str(request.user_message_id),
        "assistant_message_id": (
            str(request.assistant_message_id) if request.assistant_message_id else None
        ),
    }


def guardrail_event_fields(result: GuardrailResult) -> dict[str, Any]:
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
