import asyncio
import logging
from typing import Any
from uuid import UUID

from backend.core.observability import log_event
from backend.llm.schemas import RetrievalProvider, RetrievalResult, RetrievedChunk
from backend.rag.query import RagQueryEngine, get_default_query_engine

logger = logging.getLogger(__name__)


class RagRetrievalProvider(RetrievalProvider):
    """Adapt the sync RagQueryEngine to the async LLM retrieval protocol."""

    def __init__(
        self,
        *,
        engine: RagQueryEngine | None = None,
        top_k: int = 5,
    ) -> None:
        self._engine = engine or get_default_query_engine()
        self._top_k = top_k

    async def retrieve(
        self,
        query: str,
        *,
        user_id: UUID,
        conversation_id: UUID,
        user_message_id: UUID,
    ) -> RetrievalResult:
        try:
            raw_chunks = await asyncio.to_thread(
                self._engine.retrieve,
                query,
                top_k=self._top_k,
            )
            return RetrievalResult(
                chunks=[_retrieved_chunk_from_raw(item) for item in raw_chunks],
            )
        except Exception as exc:
            log_event(
                logger,
                "rag.retrieve.failed",
                level=logging.ERROR,
                user_id=str(user_id),
                conversation_id=str(conversation_id),
                user_message_id=str(user_message_id),
                error_type=type(exc).__name__,
                exc_info=True,
            )
            return RetrievalResult(chunks=[])


def _retrieved_chunk_from_raw(item: dict[str, Any]) -> RetrievedChunk:
    return RetrievedChunk.model_validate(item)
