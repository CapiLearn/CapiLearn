import logging
from typing import Protocol

from backend.core.observability import record_best_effort_trace_operation
from backend.rag.schemas import RagRetrievalLogRecord

logger = logging.getLogger(__name__)


class RetrievalTraceSink(Protocol):
    async def record_retrieval(self, record: RagRetrievalLogRecord) -> None: ...


class NoopRetrievalTraceSink:
    async def record_retrieval(self, record: RagRetrievalLogRecord) -> None:
        return None


class BestEffortRetrievalTraceSink:
    def __init__(self, delegate: RetrievalTraceSink) -> None:
        self._delegate = delegate

    async def record_retrieval(self, record: RagRetrievalLogRecord) -> None:
        await record_best_effort_trace_operation(
            operation_name="record_retrieval",
            operation=lambda: self._delegate.record_retrieval(record),
            sink_type=type(self._delegate).__name__,
            logger=logger,
        )
