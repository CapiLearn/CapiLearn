import logging
import threading
from uuid import uuid4

import pytest

from backend.rag.config import RagBackend, RagSettings
from backend.rag.repository import SimilarChunk
from backend.rag.retrieval import (
    ChromaRagRetrievalProvider,
    PgvectorRagRetrievalProvider,
    RagRetrievalProvider,
    build_rag_retrieval_provider,
)
from backend.rag.schemas import RetrievalProvider


@pytest.mark.asyncio
async def test_rag_retrieval_provider_calls_engine_with_configured_top_k() -> None:
    engine = FakeChromaRagQueryEngine()
    provider = ChromaRagRetrievalProvider(engine=engine, top_k=3)
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


@pytest.mark.asyncio
async def test_rag_retrieval_provider_runs_sync_engine_in_thread() -> None:
    engine = FakeChromaRagQueryEngine()
    provider = ChromaRagRetrievalProvider(engine=engine)
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
async def test_rag_retrieval_provider_degrades_to_empty_context_on_error(
    caplog,
) -> None:
    engine = FakeChromaRagQueryEngine(error=RuntimeError("vector store unavailable"))
    provider = ChromaRagRetrievalProvider(engine=engine)

    result = await provider.retrieve(
        "What is a cell?",
        user_id=uuid4(),
        conversation_id=uuid4(),
        user_message_id=uuid4(),
    )

    assert result.chunks == []
    assert "rag.retrieve.failed" in caplog.text


def test_build_rag_retrieval_provider_selects_configured_backend() -> None:
    chroma = build_rag_retrieval_provider(RagSettings(backend=RagBackend.CHROMA, top_k=3))
    pgvector = build_rag_retrieval_provider(RagSettings(backend=RagBackend.PGVECTOR, top_k=4))

    assert RagRetrievalProvider is ChromaRagRetrievalProvider
    assert isinstance(chroma, ChromaRagRetrievalProvider)
    assert chroma._top_k == 3
    assert isinstance(pgvector, PgvectorRagRetrievalProvider)
    assert pgvector._top_k == 4


@pytest.mark.asyncio
async def test_pgvector_provider_calls_rag_service_and_returns_compatible_chunks(
    caplog,
) -> None:
    caplog.set_level(logging.INFO, logger="backend.rag.retrieval")
    service = FakePgvectorService()
    provider = PgvectorRagRetrievalProvider(
        session_factory=FakeSessionFactory,
        service_factory=lambda *, session: service,
        top_k=3,
        rag_index_version="fso-2026-06",
    )
    conversation_id = uuid4()
    message_id = uuid4()

    result = await provider.retrieve(
        "What is React state?",
        user_id=uuid4(),
        conversation_id=conversation_id,
        user_message_id=message_id,
    )

    assert service.calls == [
        {
            "query_text": "What is React state?",
            "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
            "top_k": 3,
            "write_log": True,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "rag_index_version": "fso-2026-06",
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
                    "distance": 0.125,
                    "similarity": 0.875,
                },
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


@pytest.mark.asyncio
async def test_pgvector_provider_degrades_to_empty_context_on_failure(caplog) -> None:
    provider = PgvectorRagRetrievalProvider(
        session_factory=FakeSessionFactory,
        service_factory=lambda *, session: FakePgvectorService(error=RuntimeError("model failed")),
    )

    result = await provider.retrieve(
        "What is React state?",
        user_id=uuid4(),
        conversation_id=uuid4(),
        user_message_id=uuid4(),
    )

    assert result.chunks == []
    assert "rag.retrieve.failed" in caplog.text


@pytest.mark.asyncio
async def test_pgvector_provider_degrades_on_database_failure(caplog) -> None:
    provider = PgvectorRagRetrievalProvider(
        session_factory=FakeSessionFactory,
        service_factory=lambda *, session: FakePgvectorService(
            error=RuntimeError("database unavailable")
        ),
    )

    result = await provider.retrieve(
        "What is React state?",
        user_id=uuid4(),
        conversation_id=uuid4(),
        user_message_id=uuid4(),
    )

    assert result.chunks == []
    assert "database unavailable" in caplog.text


class FakeChromaRagQueryEngine:
    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error
        self.calls: list[tuple[str, int | None]] = []
        self.thread_ids: list[int] = []

    def retrieve(self, question: str, top_k: int | None = None) -> list[dict]:
        self.calls.append((question, top_k))
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

    async def retrieve_by_text(self, **kwargs):
        if self.error is not None:
            raise self.error
        self.calls.append(kwargs)
        return [self.result]
