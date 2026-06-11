import logging
import threading
from uuid import uuid4

import pytest

from backend.rag.config import RagBackend, RagEmbeddingProvider, RagSettings
from backend.rag.defaults import DEFAULT_RAG_MODEL_NAME
from backend.rag.models import EMBEDDING_DIMENSIONS
from backend.rag.repository import SimilarChunk
from backend.rag.retrieval import (
    PgvectorRagRetrievalProvider,
    build_rag_retrieval_provider,
)


def test_build_rag_retrieval_provider_builds_only_pgvector() -> None:
    pgvector = build_rag_retrieval_provider(
        RagSettings(
            _env_file=None,
            backend=RagBackend.PGVECTOR,
            embedding_provider=RagEmbeddingProvider.OPENAI,
            model_name="text-embedding-3-small",
            top_k=4,
            OPENAI_API_KEY="test-key",
        )
    )

    assert isinstance(pgvector, PgvectorRagRetrievalProvider)
    assert pgvector._top_k == 4
    assert pgvector._model_name == "text-embedding-3-small"


def test_build_rag_retrieval_provider_defensively_rejects_chroma() -> None:
    invalid_settings = RagSettings.model_construct(
        backend=RagBackend.CHROMA,
        embedding_provider=RagEmbeddingProvider.SENTENCE_TRANSFORMERS,
        model_name=DEFAULT_RAG_MODEL_NAME,
        embedding_dimensions=EMBEDDING_DIMENSIONS,
        top_k=5,
        write_retrieval_logs=True,
        index_version=None,
        openai_api_key=None,
    )

    with pytest.raises(ValueError, match="Unsupported runtime RAG backend"):
        build_rag_retrieval_provider(invalid_settings)


def test_pgvector_settings_reject_unsupported_embedding_dimensions() -> None:
    with pytest.raises(ValueError, match="current database schema stores vector\\(384\\)"):
        RagSettings(
            _env_file=None,
            backend=RagBackend.PGVECTOR,
            embedding_dimensions=1536,
        )


@pytest.mark.asyncio
async def test_pgvector_provider_calls_rag_service_and_returns_compatible_chunks(
    caplog,
) -> None:
    caplog.set_level(logging.INFO, logger="backend.rag.retrieval")
    service = FakePgvectorService()
    embedding_provider = FakeEmbeddingProvider(vector=[0.0] * EMBEDDING_DIMENSIONS)
    provider = PgvectorRagRetrievalProvider(
        session_factory=FakeSessionFactory,
        service_factory=lambda *, session: service,
        embedding_provider=embedding_provider,
        top_k=3,
    )
    conversation_id = uuid4()
    message_id = uuid4()

    result = await provider.retrieve(
        "What is React state?",
        user_id=uuid4(),
        conversation_id=conversation_id,
        user_message_id=message_id,
    )

    assert embedding_provider.calls == ["What is React state?"]
    assert service.calls == [
        {
            "query_embedding": [0.0] * EMBEDDING_DIMENSIONS,
            "embedding_model": DEFAULT_RAG_MODEL_NAME,
            "top_k": 9,
        }
    ]
    assert result.model_dump(mode="json") == {
        "chunks": [
            {
                "content": "React state stores component data.",
                "metadata": {
                    "week": "1",
                    "content_hash": "chunk-hash",
                    "char_start": 0,
                    "char_end": 34,
                    "heading_path": ["State"],
                    "section_heading": "State",
                    "chunk_type": "prose",
                    "chunk_id": str(service.result.chunk_id),
                    "document_id": str(service.result.document_id),
                    "source_type": "course_repo",
                    "source_path": "src/content/1/en/part1.md",
                    "title": "State",
                    "course_name": "Full Stack Open",
                },
                "distance": 0.125,
                "similarity": 0.875,
            }
        ]
    }
    completed = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "rag.provider.retrieve.completed"
    ]
    assert completed
    assert completed[-1].backend == "pgvector"
    assert completed[-1].chunk_count == 1
    assert completed[-1].candidate_count == 1
    assert completed[-1].retained_count == 1
    assert completed[-1].suppression_reasons == {}
    assert completed[-1].embedding_provider == "fake"
    assert completed[-1].embedding_model == DEFAULT_RAG_MODEL_NAME
    assert completed[-1].embedding_dimensions == EMBEDDING_DIMENSIONS
    assert completed[-1].latency_ms >= 0
    assert completed[-1].chunks[0]["source_path"] == "src/content/1/en/part1.md"
    assert completed[-1].chunks[0]["distance"] == 0.125
    assert completed[-1].chunks[0]["similarity"] == 0.875


@pytest.mark.asyncio
async def test_pgvector_provider_propagates_service_failure() -> None:
    provider = PgvectorRagRetrievalProvider(
        session_factory=FakeSessionFactory,
        service_factory=lambda *, session: FakePgvectorService(error=RuntimeError("model failed")),
        embedding_provider=FakeEmbeddingProvider(),
    )

    with pytest.raises(RuntimeError, match="model failed"):
        await provider.retrieve(
            "What is React state?",
            user_id=uuid4(),
            conversation_id=uuid4(),
            user_message_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_pgvector_provider_propagates_database_failure() -> None:
    provider = PgvectorRagRetrievalProvider(
        session_factory=FakeSessionFactory,
        service_factory=lambda *, session: FakePgvectorService(
            error=RuntimeError("database unavailable")
        ),
        embedding_provider=FakeEmbeddingProvider(),
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        await provider.retrieve(
            "What is React state?",
            user_id=uuid4(),
            conversation_id=uuid4(),
            user_message_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_pgvector_provider_deduplicates_candidates_before_logging(caplog) -> None:
    caplog.set_level(logging.INFO, logger="backend.rag.retrieval")
    first = _similar_chunk(content="State content", content_hash="same")
    duplicate = _similar_chunk(content="Duplicate state content", content_hash="same")
    useful = _similar_chunk(content="Props content", content_hash="different")
    service = FakePgvectorService(results=[first, duplicate, useful])
    provider = PgvectorRagRetrievalProvider(
        session_factory=FakeSessionFactory,
        service_factory=lambda *, session: service,
        embedding_provider=FakeEmbeddingProvider(),
        top_k=2,
    )

    result = await provider.retrieve(
        "What is state?",
        user_id=uuid4(),
        conversation_id=uuid4(),
        user_message_id=uuid4(),
    )

    assert [chunk.content for chunk in result.chunks] == ["State content", "Props content"]
    assert service.calls[0]["top_k"] == 6
    completed = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "rag.provider.retrieve.completed"
    ][-1]
    assert completed.candidate_count == 3
    assert completed.retained_count == 2
    assert completed.suppression_reasons == {"content_hash": 1}
    assert "State content" not in caplog.text


class FakeSessionFactory:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class FakePgvectorService:
    def __init__(
        self,
        *,
        error: Exception | None = None,
        results: list[SimilarChunk] | None = None,
    ) -> None:
        self.error = error
        self.calls = []
        self.result = _similar_chunk(content="React state stores component data.")
        self.results = results or [self.result]

    async def retrieve(self, **kwargs):
        if self.error is not None:
            raise self.error
        self.calls.append(kwargs)
        return self.results


class FakeEmbeddingProvider:
    def __init__(self, *, vector: list[float] | None = None) -> None:
        self.vector = vector or [0.0] * EMBEDDING_DIMENSIONS
        self.calls = []
        self.thread_ids = []

    @property
    def provider_name(self) -> str:
        return "fake"

    @property
    def model_name(self) -> str:
        return DEFAULT_RAG_MODEL_NAME

    @property
    def dimensions(self) -> int:
        return len(self.vector)

    def embed_text(self, query_text: str) -> list[float]:
        self.calls.append(query_text)
        self.thread_ids.append(threading.get_ident())
        return self.vector

    def embed_texts(self, query_texts: list[str]) -> list[list[float]]:
        return [self.embed_text(text) for text in query_texts]


def _similar_chunk(
    *,
    content: str,
    content_hash: str = "chunk-hash",
) -> SimilarChunk:
    return SimilarChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        content=content,
        metadata={
            "week": "1",
            "content_hash": content_hash,
            "char_start": 0,
            "char_end": len(content),
            "heading_path": ["State"],
            "section_heading": "State",
            "chunk_type": "prose",
        },
        source_type="course_repo",
        source_path="src/content/1/en/part1.md",
        title="State",
        course_name="Full Stack Open",
        distance=0.125,
        similarity=0.875,
    )
