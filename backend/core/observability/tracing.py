import logging
from typing import Any

logger = logging.getLogger(__name__)


class LLMTraceSink:
    async def start_chat_turn(self, metadata: dict[str, Any]) -> None:
        await self._safe_record("start_chat_turn", metadata)

    async def record_guardrail(self, metadata: dict[str, Any]) -> None:
        await self._safe_record("record_guardrail", metadata)

    async def record_retrieval(self, metadata: dict[str, Any]) -> None:
        await self._safe_record("record_retrieval", metadata)

    async def record_generation(self, metadata: dict[str, Any]) -> None:
        await self._safe_record("record_generation", metadata)

    async def record_error(self, metadata: dict[str, Any]) -> None:
        await self._safe_record("record_error", metadata)

    async def finish_chat_turn(self, metadata: dict[str, Any]) -> None:
        await self._safe_record("finish_chat_turn", metadata)

    async def _safe_record(self, operation: str, metadata: dict[str, Any]) -> None:
        try:
            await getattr(self, f"_{operation}")(metadata)
        except Exception as exc:
            logger.warning(
                "llm.trace_sink.failed",
                extra={
                    "event": "llm.trace_sink.failed",
                    "trace_operation": operation,
                    "sink_type": type(self).__name__,
                    "error_type": type(exc).__name__,
                },
                exc_info=True,
            )

    async def _start_chat_turn(self, metadata: dict[str, Any]) -> None:
        return None

    async def _record_guardrail(self, metadata: dict[str, Any]) -> None:
        return None

    async def _record_retrieval(self, metadata: dict[str, Any]) -> None:
        return None

    async def _record_generation(self, metadata: dict[str, Any]) -> None:
        return None

    async def _record_error(self, metadata: dict[str, Any]) -> None:
        return None

    async def _finish_chat_turn(self, metadata: dict[str, Any]) -> None:
        return None


class NoopLLMTraceSink(LLMTraceSink):
    pass
