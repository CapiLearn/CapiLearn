import asyncio
import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import SessionFactory
from backend.core.observability import elapsed_ms, log_event, timer_start
from backend.rag.config import RagBackend, RagSettings
from backend.rag.deduplication import DeduplicationResult, deduplicate_chunks
from backend.rag.defaults import (
    DEFAULT_RAG_EMBEDDING_DIMENSIONS,
    DEFAULT_RAG_MODEL_NAME,
    DEFAULT_RAG_TOP_K,
)
from backend.rag.embeddings import (
    QueryEmbeddingProvider,
    build_embedding_provider,
)
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


class PgvectorRagRetrievalProvider(RetrievalProvider):
    def __init__(
        self,
        *,
        model_name: str = DEFAULT_RAG_MODEL_NAME,
        embedding_dimensions: int = DEFAULT_RAG_EMBEDDING_DIMENSIONS,
        top_k: int = DEFAULT_RAG_TOP_K,
        session_factory: SessionFactoryCallable = SessionFactory,
        service_factory: RagServiceFactory = RagService,
        embedding_provider: QueryEmbeddingProvider | None = None,
    ) -> None:
        self._model_name = model_name
        self._embedding_dimensions = embedding_dimensions
        self._top_k = top_k
        self._session_factory = session_factory
        self._service_factory = service_factory
        if embedding_provider is None:
            raise ValueError("Pgvector retrieval requires a configured embedding provider.")
        self._embedding_provider = embedding_provider

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
            embedding_provider=self._embedding_provider.provider_name,
            embedding_model=self._model_name,
            embedding_dimensions=self._embedding_dimensions,
        )
        return result

    def _embed_query(self, query: str) -> list[float]:
        embedding = self._embedding_provider.embed_text(query)
        if len(embedding) != self._embedding_dimensions:
            raise ValueError(
                f"Query embedding has {len(embedding)} dimensions; "
                f"expected {self._embedding_dimensions}."
            )
        return embedding


def build_rag_retrieval_provider(config: RagSettings) -> RetrievalProvider:
    if config.backend != RagBackend.PGVECTOR:
        raise ValueError(f"Unsupported runtime RAG backend: {config.backend!r}")
    embedding_provider = build_embedding_provider(config)
    return PgvectorRagRetrievalProvider(
        model_name=config.model_name,
        embedding_dimensions=config.embedding_dimensions,
        top_k=config.top_k,
        embedding_provider=embedding_provider,
    )


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
    embedding_provider: str | None = None,
    embedding_model: str | None = None,
    embedding_dimensions: int | None = None,
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
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
        embedding_dimensions=embedding_dimensions,
        chunks=[retrieval_chunk_log_metadata(chunk) for chunk in result.chunks[:5]],
        user_id=str(user_id),
        conversation_id=str(conversation_id),
        user_message_id=str(user_message_id),
    )
