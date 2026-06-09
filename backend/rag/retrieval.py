import asyncio
import logging
from typing import Any
from uuid import UUID

from backend.core.database import SessionFactory
from backend.core.observability import elapsed_ms, log_event, timer_start
from backend.rag.config import RagBackend, RagSettings
from backend.rag.defaults import DEFAULT_RAG_MODEL_NAME, DEFAULT_RAG_TOP_K
from backend.rag.embeddings import QueryEmbeddingProvider, get_embedding_provider
from backend.rag.query import ChromaRagConfig, ChromaRagQueryEngine
from backend.rag.schemas import RetrievalProvider, RetrievalResult, RetrievedChunk
from backend.rag.service import RagService

logger = logging.getLogger(__name__)


class ChromaRagRetrievalProvider(RetrievalProvider):
    """Adapt the sync Chroma query engine to the async retrieval protocol."""

    def __init__(
        self,
        *,
        engine: ChromaRagQueryEngine | None = None,
        model_name: str = DEFAULT_RAG_MODEL_NAME,
        top_k: int | None = None,
        embedding_provider: QueryEmbeddingProvider | None = None,
    ) -> None:
        engine_top_k = DEFAULT_RAG_TOP_K if top_k is None else top_k
        self._engine = engine or ChromaRagQueryEngine(
            ChromaRagConfig(model_name=model_name, top_k=engine_top_k)
        )
        self._model_name = self._engine.config.model_name
        self._top_k = top_k
        self._embedding_provider = embedding_provider or get_embedding_provider()

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
                self._retrieve_raw,
                query,
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

    def _retrieve_raw(self, query: str) -> list[dict]:
        query_embedding = self._embedding_provider.embed_query(
            query,
            model_name=self._model_name,
        )
        return self._engine.retrieve_by_embedding(
            query_embedding,
            top_k=self._top_k,
        )


class PgvectorRagRetrievalProvider(RetrievalProvider):
    def __init__(
        self,
        *,
        model_name: str = DEFAULT_RAG_MODEL_NAME,
        top_k: int = DEFAULT_RAG_TOP_K,
        write_retrieval_logs: bool = True,
        rag_index_version: str | None = None,
        session_factory=SessionFactory,
        service_factory=RagService,
        embedding_provider: QueryEmbeddingProvider | None = None,
    ) -> None:
        self._model_name = model_name
        self._top_k = top_k
        self._write_retrieval_logs = write_retrieval_logs
        self._rag_index_version = rag_index_version
        self._session_factory = session_factory
        self._service_factory = service_factory
        self._embedding_provider = embedding_provider or get_embedding_provider()

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
            query_embedding = await asyncio.to_thread(
                self._embed_query,
                query,
            )
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
        return self._embedding_provider.embed_query(
            query,
            model_name=self._model_name,
        )


def build_rag_retrieval_provider(config: RagSettings) -> RetrievalProvider:
    if config.backend == RagBackend.PGVECTOR:
        return PgvectorRagRetrievalProvider(
            model_name=config.model_name,
            top_k=config.top_k,
            write_retrieval_logs=config.write_retrieval_logs,
            rag_index_version=config.index_version,
        )
    return ChromaRagRetrievalProvider(model_name=config.model_name, top_k=config.top_k)


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
