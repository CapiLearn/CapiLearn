import asyncio
import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import SessionFactory
from backend.core.observability import elapsed_ms, log_event, timer_start
from backend.rag.config import RagBackend, RagSettings
from backend.rag.deduplication import DeduplicationResult, deduplicate_chunks
from backend.rag.defaults import (
    DEFAULT_RAG_MODEL_NAME,
    DEFAULT_RAG_TOP_K,
    validate_pgvector_model_name,
)
from backend.rag.embeddings import QueryEmbeddingProvider, get_embedding_provider
from backend.rag.query import ChromaRagConfig, ChromaRagQueryEngine
from backend.rag.repository import SimilarChunk
from backend.rag.schemas import (
    RetrievalProvider,
    RetrievalResult,
    RetrievedChunk,
    retrieval_chunk_log_metadata,
)
from backend.rag.service import RagService

logger = logging.getLogger(__name__)

SessionFactoryCallable = Callable[[], AbstractAsyncContextManager[AsyncSession]]
RagServiceFactory = Callable[..., RagService]


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
        if engine is not None and embedding_provider is not None:
            raise ValueError("Pass either engine or embedding_provider, not both.")
        engine_top_k = DEFAULT_RAG_TOP_K if top_k is None else top_k
        self._engine = engine or ChromaRagQueryEngine(
            ChromaRagConfig(model_name=model_name, top_k=engine_top_k),
            embedding_provider=embedding_provider,
        )
        self._model_name = self._engine.config.model_name
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
        raw_chunks = await asyncio.to_thread(
            self._retrieve_raw,
            query,
        )
        deduplicated = deduplicate_chunks(
            [_retrieved_chunk_from_raw(item) for item in raw_chunks],
            top_k=self._effective_top_k,
        )
        result = RetrievalResult(chunks=deduplicated.chunks)
        _log_retrieval_completed(
            backend=RagBackend.CHROMA,
            result=result,
            started_at=started_at,
            user_id=user_id,
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            deduplication=deduplicated,
        )
        return result

    def _retrieve_raw(self, query: str) -> list[dict[str, Any]]:
        return self._engine.retrieve(
            query,
            top_k=self._candidate_top_k,
        )

    @property
    def _effective_top_k(self) -> int:
        return self._engine.config.top_k if self._top_k is None else self._top_k

    @property
    def _candidate_top_k(self) -> int:
        return min(self._effective_top_k * 3, 50)


class PgvectorRagRetrievalProvider(RetrievalProvider):
    def __init__(
        self,
        *,
        model_name: str = DEFAULT_RAG_MODEL_NAME,
        top_k: int = DEFAULT_RAG_TOP_K,
        session_factory: SessionFactoryCallable = SessionFactory,
        service_factory: RagServiceFactory = RagService,
        embedding_provider: QueryEmbeddingProvider | None = None,
    ) -> None:
        self._model_name = validate_pgvector_model_name(model_name)
        self._top_k = top_k
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
        query_embedding = await asyncio.to_thread(
            self._embed_query,
            query,
        )
        async with self._session_factory() as session:
            service = self._service_factory(session=session)
            rows = await service.retrieve(
                query_embedding=query_embedding,
                embedding_model=self._model_name,
                top_k=min(self._top_k * 3, 50),
            )
        deduplicated = deduplicate_chunks(
            [_retrieved_chunk_from_similar_chunk(row) for row in rows],
            top_k=self._top_k,
        )
        result = RetrievalResult(chunks=deduplicated.chunks)
        _log_retrieval_completed(
            backend=RagBackend.PGVECTOR,
            result=result,
            started_at=started_at,
            user_id=user_id,
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            deduplication=deduplicated,
        )
        return result

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
        )
    return ChromaRagRetrievalProvider(model_name=config.model_name, top_k=config.top_k)


def _retrieved_chunk_from_raw(item: dict[str, Any]) -> RetrievedChunk:
    return RetrievedChunk.model_validate(item)


def _retrieved_chunk_from_similar_chunk(row: SimilarChunk) -> RetrievedChunk:
    return RetrievedChunk(
        content=row.content,
        metadata={
            **row.metadata,
            "chunk_id": str(row.chunk_id),
            "document_id": str(row.document_id),
            "source_type": row.source_type,
            "source_path": row.source_path,
            "title": row.title,
            "course_name": row.course_name,
        },
        distance=row.distance,
        similarity=row.similarity,
    )


def _log_retrieval_completed(
    *,
    backend: RagBackend,
    result: RetrievalResult,
    started_at: float,
    user_id: UUID,
    conversation_id: UUID,
    user_message_id: UUID,
    deduplication: DeduplicationResult,
) -> None:
    log_event(
        logger,
        "rag.provider.retrieve.completed",
        backend=backend.value,
        latency_ms=elapsed_ms(started_at),
        chunk_count=len(result.chunks),
        candidate_count=deduplication.candidate_count,
        retained_count=len(result.chunks),
        suppression_reasons=deduplication.suppression_reasons,
        chunks=[retrieval_chunk_log_metadata(chunk) for chunk in result.chunks[:5]],
        user_id=str(user_id),
        conversation_id=str(conversation_id),
        user_message_id=str(user_message_id),
    )
