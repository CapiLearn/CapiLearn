import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)

TraceOperation = Callable[[], Awaitable[None]]


class TraceSinkContractError(Exception):
    pass


class LLMTraceOperation(StrEnum):
    START_CHAT_TURN = "start_chat_turn"
    RECORD_GUARDRAIL = "record_guardrail"
    RECORD_GENERATION = "record_generation"
    RECORD_REPAIR = "record_repair"
    RECORD_ERROR = "record_error"
    FINISH_CHAT_TURN = "finish_chat_turn"


class LLMTraceSink(ABC):
    @abstractmethod
    async def record(
        self,
        operation: LLMTraceOperation,
        metadata: dict[str, Any],
    ) -> None:
        raise NotImplementedError


class NoopLLMTraceSink(LLMTraceSink):
    async def record(
        self,
        operation: LLMTraceOperation,
        metadata: dict[str, Any],
    ) -> None:
        return None


class BestEffortLLMTraceSink(LLMTraceSink):
    def __init__(self, delegate: LLMTraceSink) -> None:
        self._delegate = delegate

    async def record(
        self,
        operation: LLMTraceOperation,
        metadata: dict[str, Any],
    ) -> None:
        await record_best_effort_trace_operation(
            operation_name=operation.value,
            operation=lambda: self._delegate.record(operation, metadata),
            sink_type=type(self._delegate).__name__,
            logger=logger,
        )


async def record_best_effort_trace_operation(
    *,
    operation_name: str,
    operation: TraceOperation,
    sink_type: str,
    logger: logging.Logger,
) -> None:
    try:
        await operation()
    except TraceSinkContractError:
        raise
    except Exception as exc:
        logger.warning(
            "trace_sink.failed",
            extra={
                "event": "trace_sink.failed",
                "trace_operation": operation_name,
                "sink_type": sink_type,
                "error_type": type(exc).__name__,
            },
            exc_info=exc,
        )
