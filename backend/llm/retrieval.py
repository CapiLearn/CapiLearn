import asyncio
import logging
from collections.abc import Callable
from threading import Lock
from typing import Any
from uuid import UUID

from sentence_transformers import SentenceTransformer

from backend.core.database import SessionFactory
from backend.core.observability import elapsed_ms, log_event, timer_start
from backend.llm.schemas import RetrievalProvider, RetrievalResult, RetrievedChunk
from backend.rag.config import RagBackend, RagSettings
from backend.rag.query import RagQueryEngine, get_default_query_engine
from backend.rag.service import RagService

logger = logging.getLogger(__name__)


class RagRetrievalProvider(RetrievalProvider):
    """Adapt the sync Chroma query engine to the async retrieval protocol."""

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
        started_at = timer_start()
        try:
            raw_chunks = await asyncio.to_thread(
                self._engine.retrieve,
                query,
                top_k=self._top_k,
            )
            result = RetrievalResult(
                chunks=[_retrieved_chunk_from_raw(item) for item in raw_chunks],
            )
            _log_retrieval_completed(
                backend=RagBackend.CHROMA,
                result=result,
                started_at=started_at,
                user_id=user_id,
                conversation_id=conversation_id,
                user_message_id=user_message_id,
            )
            return result
        except Exception as exc:
            _log_retrieval_failed(
                backend=RagBackend.CHROMA,
                exc=exc,
                started_at=started_at,
                user_id=str(user_id),
                conversation_id=str(conversation_id),
                user_message_id=str(user_message_id),
            )
            return RetrievalResult(chunks=[])


class PgvectorRagRetrievalProvider(RetrievalProvider):
    def __init__(
        self,
        *,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        top_k: int = 5,
        write_retrieval_logs: bool = True,
        rag_index_version: str | None = None,
        model_loader: Callable[[str], Any] = SentenceTransformer,
        session_factory=SessionFactory,
        service_factory=RagService,
    ) -> None:
        self._model_name = model_name
        self._top_k = top_k
        self._write_retrieval_logs = write_retrieval_logs
        self._rag_index_version = rag_index_version
        self._model_loader = model_loader
        self._session_factory = session_factory
        self._service_factory = service_factory
        self._model: Any | None = None
        self._model_lock = Lock()

    async def retrieve(
        self,
        query: str,
        *,
        user_id: UUID,
        conversation_id: UUID,
        user_message_id: UUID,
    ) -> RetrievalResult:
        started_at = timer_start()
        try:
            query_embedding = await asyncio.to_thread(self._embed_query, query)
            async with self._session_factory() as session:
                service = self._service_factory(session=session)
                rows = await service.retrieve(
                    query_text=query,
                    query_embedding=query_embedding,
                    embedding_model=self._model_name,
                    top_k=self._top_k,
                    write_log=self._write_retrieval_logs,
                    conversation_id=conversation_id,
                    message_id=user_message_id,
                    rag_index_version=self._rag_index_version,
                )
            result = RetrievalResult(
                chunks=[_retrieved_chunk_from_raw(row.to_retrieval_dict()) for row in rows],
            )
            _log_retrieval_completed(
                backend=RagBackend.PGVECTOR,
                result=result,
                started_at=started_at,
                user_id=user_id,
                conversation_id=conversation_id,
                user_message_id=user_message_id,
            )
            return result
        except Exception as exc:
            _log_retrieval_failed(
                backend=RagBackend.PGVECTOR,
                exc=exc,
                started_at=started_at,
                user_id=str(user_id),
                conversation_id=str(conversation_id),
                user_message_id=str(user_message_id),
            )
            return RetrievalResult(chunks=[])

    def _embed_query(self, query: str) -> list[float]:
        model = self._get_model()
        embedding = model.encode(query)
        return embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)

    def _get_model(self) -> Any:
        if self._model is None:
            with self._model_lock:
                if self._model is None:
                    self._model = self._model_loader(self._model_name)
        return self._model


def build_rag_retrieval_provider(config: RagSettings) -> RetrievalProvider:
    if config.backend == RagBackend.PGVECTOR:
        return PgvectorRagRetrievalProvider(
            model_name=config.model_name,
            top_k=config.top_k,
            write_retrieval_logs=config.write_retrieval_logs,
            rag_index_version=config.index_version,
        )
    return RagRetrievalProvider(top_k=config.top_k)


def _retrieved_chunk_from_raw(item: dict[str, Any]) -> RetrievedChunk:
    return RetrievedChunk.model_validate(item)


def _log_retrieval_completed(
    *,
    backend: RagBackend,
    result: RetrievalResult,
    started_at: float,
    user_id: UUID,
    conversation_id: UUID,
    user_message_id: UUID,
) -> None:
    log_event(
        logger,
        "rag.provider.retrieve.completed",
        backend=backend.value,
        latency_ms=elapsed_ms(started_at),
        chunk_count=len(result.chunks),
        chunks=[_chunk_log_metadata(chunk) for chunk in result.chunks[:5]],
        user_id=str(user_id),
        conversation_id=str(conversation_id),
        user_message_id=str(user_message_id),
    )


def _log_retrieval_failed(
    *,
    backend: RagBackend,
    exc: Exception,
    started_at: float,
    user_id: str,
    conversation_id: str,
    user_message_id: str,
) -> None:
    log_event(
        logger,
        "rag.retrieve.failed",
        level=logging.ERROR,
        backend=backend.value,
        latency_ms=elapsed_ms(started_at),
        user_id=user_id,
        conversation_id=conversation_id,
        user_message_id=user_message_id,
        error_type=type(exc).__name__,
        exc_info=True,
    )


def _chunk_log_metadata(chunk: RetrievedChunk) -> dict[str, Any]:
    metadata = chunk.metadata or {}
    keys = (
        "chunk_id",
        "document_id",
        "source_path",
        "title",
        "distance",
        "similarity",
    )
    return {key: metadata[key] for key in keys if key in metadata}
