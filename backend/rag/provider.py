import asyncio
from collections.abc import Callable
from typing import Any
from uuid import UUID

from backend.llm.schemas import RetrievalProvider, RetrievalResult, RetrievedChunk

RetrieveContextFn = Callable[[str, Any, Any, int], list[dict[str, Any]]]


class ChromaRetrievalProvider(RetrievalProvider):
    """Adapt sync RAG retrieve_context calls to the async LLM retrieval protocol."""

    def __init__(
        self,
        *,
        collection: Any,
        model: Any,
        retrieve_context_fn: RetrieveContextFn,
        top_k: int = 5,
    ) -> None:
        self._collection = collection
        self._model = model
        self._retrieve_context_fn = retrieve_context_fn
        self._top_k = top_k

    async def retrieve(
        self,
        query: str,
        *,
        user_id: UUID,
        conversation_id: UUID,
        user_message_id: UUID,
    ) -> RetrievalResult:
        raw_chunks = await asyncio.to_thread(
            self._retrieve_context_fn,
            query,
            self._collection,
            self._model,
            self._top_k,
        )
        return RetrievalResult(
            chunks=[_retrieved_chunk_from_raw(item) for item in raw_chunks],
        )


def _retrieved_chunk_from_raw(item: dict[str, Any]) -> RetrievedChunk:
    return RetrievedChunk.model_validate(item)
