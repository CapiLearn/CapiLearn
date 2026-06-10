import logging
import threading
from uuid import uuid4

import pytest

from backend.rag.config import RagBackend, RagSettings
from backend.rag.defaults import DEFAULT_RAG_MODEL_NAME
from backend.rag.models import EMBEDDING_DIMENSIONS
from backend.rag.repository import SimilarChunk
from backend.rag.retrieval import (
    ChromaRagRetrievalProvider,
    PgvectorRagRetrievalProvider,
    build_rag_retrieval_provider,
)
from backend.rag.schemas import RetrievalProvider


@pytest.mark.asyncio
async def test_rag_retrieval_provider_delegates_to_configured_engine() -> None:
    engine = FakeChromaRagQueryEngine()
    provider = ChromaRagRetrievalProvider(
        engine=engine,
        top_k=3,
    )
    retrieval_provider: RetrievalProvider = provider

    result = await retrieval_provider.retrieve(
        "What is a cell?",
        user_id=uuid4(),
        conversation_id=uuid4(),
        user_message_id=uuid4(),
    )

    assert engine.calls == [("What is a cell?", 3)]
    assert len(result.chunks) == 1
    assert result.chunks[0].content == "Retrieved course chunk."
    assert result.chunks[0].metadata == {
        "source_id": "doc_1",
        "title": "Course Notes",
    }
    assert result.chunks[0].distance == 0.18
    assert result.chunks[0].similarity is None


@pytest.mark.asyncio
async def test_rag_retrieval_provider_runs_sync_engine_in_thread() -> None:
    engine = FakeChromaRagQueryEngine()
    provider = ChromaRagRetrievalProvider(
        engine=engine,
    )
    loop_thread_id = threading.get_ident()

    result = await provider.retrieve(
        "What is a cell?",
        user_id=uuid4(),
        conversation_id=uuid4(),
        user_message_id=uuid4(),
    )

    assert result.chunks
    assert engine.thread_ids
    assert engine.thread_ids[0] != loop_thread_id


@pytest.mark.asyncio
async def test_rag_retrieval_provider_propagates_engine_error() -> None:
    engine = FakeChromaRagQueryEngine(error=RuntimeError("vector store unavailable"))
    provider = ChromaRagRetrievalProvider(
        engine=engine,
    )

    with pytest.raises(RuntimeError, match="vector store unavailable"):
        await provider.retrieve(
            "What is a cell?",
            user_id=uuid4(),
            conversation_id=uuid4(),
            user_message_id=uuid4(),
        )


def test_chroma_provider_rejects_ignored_embedding_provider() -> None:
    with pytest.raises(ValueError, match="Pass either engine or embedding_provider"):
        ChromaRagRetrievalProvider(
            engine=FakeChromaRagQueryEngine(),
            embedding_provider=FakeEmbeddingProvider(),
        )


def test_build_rag_retrieval_provider_selects_configured_backend() -> None:
    chroma = build_rag_retrieval_provider(
        RagSettings(
            backend=RagBackend.CHROMA,
            model_name="custom-chroma-model",
            top_k=3,
        )
    )
    pgvector = build_rag_retrieval_provider(
        RagSettings(
            backend=RagBackend.PGVECTOR,
            top_k=4,
        )
    )

    assert isinstance(chroma, ChromaRagRetrievalProvider)
    assert chroma._model_name == "custom-chroma-model"
    assert chroma._engine.config.model_name == "custom-chroma-model"
    assert chroma._engine.config.top_k == 3
    assert chroma._top_k == 3
    assert isinstance(pgvector, PgvectorRagRetrievalProvider)
    assert pgvector._top_k == 4
    assert pgvector._model_name == DEFAULT_RAG_MODEL_NAME


def test_pgvector_settings_reject_unsupported_embedding_model() -> None:
    with pytest.raises(ValueError, match="database schema stores 384-dimensional"):
        RagSettings(
            backend=RagBackend.PGVECTOR,
            model_name="custom-pgvector-model",
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

    assert embedding_provider.calls == [
        {"query_text": "What is React state?", "model_name": DEFAULT_RAG_MODEL_NAME}
    ]
    assert service.calls == [
        {
            "query_embedding": [0.0] * EMBEDDING_DIMENSIONS,
            "embedding_model": DEFAULT_RAG_MODEL_NAME,
            "top_k": 3,
        }
    ]
    assert result.model_dump(mode="json") == {
        "chunks": [
            {
                "content": "React state stores component data.",
                "metadata": {
                    "week": "1",
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


class FakeChromaRagQueryEngine:
    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error
        self.config = FakeChromaRagConfig()
        self.calls: list[tuple[str, int | None]] = []
        self.thread_ids: list[int] = []

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
    ) -> list[dict]:
        self.calls.append((query, top_k))
        self.thread_ids.append(threading.get_ident())
        if self._error is not None:
            raise self._error
        return [
            {
                "content": "Retrieved course chunk.",
                "metadata": {"source_id": "doc_1", "title": "Course Notes"},
                "distance": 0.18,
            }
        ]


class FakeChromaRagConfig:
    model_name = DEFAULT_RAG_MODEL_NAME
    top_k = 5


class FakeSessionFactory:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class FakePgvectorService:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls = []
        self.result = SimilarChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            content="React state stores component data.",
            metadata={"week": "1"},
            source_type="course_repo",
            source_path="src/content/1/en/part1.md",
            title="State",
            course_name="Full Stack Open",
            distance=0.125,
            similarity=0.875,
        )

    async def retrieve(self, **kwargs):
        if self.error is not None:
            raise self.error
        self.calls.append(kwargs)
        return [self.result]


class FakeEmbeddingProvider:
    def __init__(self, *, vector: list[float] | None = None) -> None:
        self.vector = vector or [0.0] * EMBEDDING_DIMENSIONS
        self.calls = []
        self.thread_ids = []

    def embed_query(self, query_text: str, *, model_name: str) -> list[float]:
        self.calls.append({"query_text": query_text, "model_name": model_name})
        self.thread_ids.append(threading.get_ident())
        return self.vector
