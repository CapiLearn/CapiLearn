import threading
from uuid import uuid4

import pytest

from backend.llm.retrieval import RagRetrievalProvider
from backend.llm.schemas import RetrievalProvider


@pytest.mark.asyncio
async def test_rag_retrieval_provider_calls_engine_with_configured_top_k() -> None:
    engine = FakeRagQueryEngine()
    provider = RagRetrievalProvider(engine=engine, top_k=3)
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
    engine = FakeRagQueryEngine()
    provider = RagRetrievalProvider(engine=engine)
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
    engine = FakeRagQueryEngine(error=RuntimeError("vector store unavailable"))
    provider = RagRetrievalProvider(engine=engine)

    result = await provider.retrieve(
        "What is a cell?",
        user_id=uuid4(),
        conversation_id=uuid4(),
        user_message_id=uuid4(),
    )

    assert result.chunks == []
    assert "rag.retrieve.failed" in caplog.text


class FakeRagQueryEngine:
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
