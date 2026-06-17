import importlib
import logging
import sys
import threading
from uuid import uuid4

import pytest

from backend.rag.config import RagBackend, RagSettings
from backend.rag.defaults import DEFAULT_RAG_EMBEDDING_PROVIDER, DEFAULT_RAG_MODEL_NAME
from backend.rag.models import EMBEDDING_DIMENSIONS
from backend.rag.repository import SimilarChunk
from backend.rag.retrieval import (
    PgvectorRagRetrievalProvider,
    build_rag_retrieval_provider,
    candidate_pool_size,
)


def test_rag_settings_reject_chroma_runtime_fallback() -> None:
    with pytest.raises(ValueError, match="Unsupported RAG backend"):
        RagSettings(
            backend=RagBackend.CHROMA,
            model_name="custom-chroma-model",
            top_k=3,
        )


def test_chat_rag_startup_does_not_import_local_vector_dependencies() -> None:
    sys.modules.pop("chromadb", None)
    sys.modules.pop("sentence_transformers", None)

    importlib.import_module("backend.chat.dependencies")

    assert "chromadb" not in sys.modules
    assert "sentence_transformers" not in sys.modules


def test_build_rag_retrieval_provider_selects_pgvector_backend(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    pgvector = build_rag_retrieval_provider(
        RagSettings(
            backend=RagBackend.PGVECTOR,
            top_k=4,
        )
    )

    assert isinstance(pgvector, PgvectorRagRetrievalProvider)
    assert pgvector._top_k == 4
    assert pgvector._embedding_provider_name == DEFAULT_RAG_EMBEDDING_PROVIDER
    assert pgvector._model_name == DEFAULT_RAG_MODEL_NAME


def test_pgvector_settings_reject_unsupported_embedding_model() -> None:
    with pytest.raises(ValueError, match="RAG_MODEL_NAME"):
        RagSettings(
            backend=RagBackend.PGVECTOR,
            model_name="custom-pgvector-model",
        )


def test_pgvector_settings_reject_non_openai_embedding_provider() -> None:
    with pytest.raises(ValueError, match="local embedding fallback is not supported"):
        RagSettings(
            backend=RagBackend.PGVECTOR,
            embedding_provider="sentence-transformers",
        )


def test_rag_settings_reject_top_k_above_max_candidates() -> None:
    with pytest.raises(ValueError, match="RAG_TOP_K"):
        RagSettings(top_k=51, max_candidates=50)


def test_rag_settings_reject_non_positive_candidate_multiplier() -> None:
    with pytest.raises(ValueError, match="greater than or equal to 1"):
        RagSettings(candidate_pool_multiplier=0)


def test_rag_settings_reject_non_positive_max_candidates() -> None:
    with pytest.raises(ValueError, match="greater than or equal to 1"):
        RagSettings(max_candidates=0)


def test_candidate_pool_is_capped_at_configured_maximum() -> None:
    assert candidate_pool_size(20, 3, 50) == 50


@pytest.mark.asyncio
async def test_pgvector_provider_uses_configured_candidate_pool() -> None:
    pgvector_service = FakePgvectorService()
    pgvector = PgvectorRagRetrievalProvider(
        top_k=2,
        candidate_pool_multiplier=4,
        max_candidates=7,
        session_factory=FakeSessionFactory,
        service_factory=lambda *, session: pgvector_service,
        embedding_provider=FakeEmbeddingProvider(),
    )

    await pgvector.retrieve(
        "Question",
        user_id=uuid4(),
        conversation_id=uuid4(),
        user_message_id=uuid4(),
    )

    assert pgvector_service.calls[0]["top_k"] == 7


@pytest.mark.parametrize(
    ("provider_type", "kwargs", "message"),
    [
        (PgvectorRagRetrievalProvider, {"max_candidates": 0}, "max_candidates"),
        (
            PgvectorRagRetrievalProvider,
            {"top_k": 51, "max_candidates": 50},
            "less than or equal",
        ),
    ],
)
def test_direct_provider_construction_rejects_invalid_candidate_settings(
    provider_type,
    kwargs,
    message,
) -> None:
    with pytest.raises(ValueError, match=message):
        provider_type(**kwargs)


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

    assert embedding_provider.calls == [
        {"query_text": "What is React state?", "model_name": DEFAULT_RAG_MODEL_NAME}
    ]
    assert service.calls == [
        {
            "query_embedding": [0.0] * EMBEDDING_DIMENSIONS,
            "embedding_provider": DEFAULT_RAG_EMBEDDING_PROVIDER,
            "embedding_model": DEFAULT_RAG_MODEL_NAME,
            "embedding_dimensions": EMBEDDING_DIMENSIONS,
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

    def embed_query(self, query_text: str, *, model_name: str) -> list[float]:
        self.calls.append({"query_text": query_text, "model_name": model_name})
        self.thread_ids.append(threading.get_ident())
        return self.vector


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
