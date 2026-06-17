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
    DEFAULT_RAG_CANDIDATE_POOL_MULTIPLIER,
    DEFAULT_RAG_EMBEDDING_DIMENSIONS,
    DEFAULT_RAG_EMBEDDING_PROVIDER,
    DEFAULT_RAG_MAX_CANDIDATES,
    DEFAULT_RAG_MODEL_NAME,
    DEFAULT_RAG_TOP_K,
    validate_pgvector_embedding_contract,
)
from backend.rag.embeddings import QueryEmbeddingProvider, get_embedding_provider
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


def candidate_pool_size(
    top_k: int,
    candidate_pool_multiplier: int,
    max_candidates: int,
) -> int:
    if top_k < 1:
        raise ValueError("top_k must be at least 1")
    if candidate_pool_multiplier < 1:
        raise ValueError("candidate_pool_multiplier must be at least 1")
    if max_candidates < 1:
        raise ValueError("max_candidates must be at least 1")
    if top_k > max_candidates:
        raise ValueError("top_k must be less than or equal to max_candidates")
    return min(top_k * candidate_pool_multiplier, max_candidates)


class PgvectorRagRetrievalProvider(RetrievalProvider):
    def __init__(
        self,
        *,
        embedding_provider_name: str = DEFAULT_RAG_EMBEDDING_PROVIDER,
        model_name: str = DEFAULT_RAG_MODEL_NAME,
        embedding_dimensions: int = DEFAULT_RAG_EMBEDDING_DIMENSIONS,
        top_k: int = DEFAULT_RAG_TOP_K,
        candidate_pool_multiplier: int = DEFAULT_RAG_CANDIDATE_POOL_MULTIPLIER,
        max_candidates: int = DEFAULT_RAG_MAX_CANDIDATES,
        session_factory: SessionFactoryCallable = SessionFactory,
        service_factory: RagServiceFactory = RagService,
        embedding_provider: QueryEmbeddingProvider | None = None,
    ) -> None:
        self._embedding_provider_name, self._model_name, self._embedding_dimensions = (
            validate_pgvector_embedding_contract(
                embedding_provider=embedding_provider_name,
                model_name=model_name,
                embedding_dimensions=embedding_dimensions,
            )
        )
        candidate_pool_size(top_k, candidate_pool_multiplier, max_candidates)
        self._top_k = top_k
        self._candidate_pool_multiplier = candidate_pool_multiplier
        self._max_candidates = max_candidates
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
                embedding_provider=self._embedding_provider_name,
                embedding_model=self._model_name,
                embedding_dimensions=self._embedding_dimensions,
                top_k=candidate_pool_size(
                    self._top_k,
                    self._candidate_pool_multiplier,
                    self._max_candidates,
                ),
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
            embedding_provider_name=config.embedding_provider,
            model_name=config.model_name,
            embedding_dimensions=config.embedding_dimensions,
            top_k=config.top_k,
            candidate_pool_multiplier=config.candidate_pool_multiplier,
            max_candidates=config.max_candidates,
        )
    raise ValueError("Unsupported RAG backend. Configure RAG_BACKEND=pgvector.")


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
