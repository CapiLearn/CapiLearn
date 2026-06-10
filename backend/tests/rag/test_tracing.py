from uuid import uuid4

import pytest

from backend.rag.schemas import (
    RagRetrievalLogRecord,
    RetrievalResult,
    RetrievedChunk,
    build_rag_retrieval_log_record,
)
from backend.rag.tracing import PostgresRagTraceSink


def test_build_rag_retrieval_log_record_maps_retrieval_result() -> None:
    conversation_id = uuid4()
    message_id = uuid4()
    chunk_id = uuid4()
    document_id = uuid4()

    record = build_rag_retrieval_log_record(
        query_text="What is state?",
        conversation_id=conversation_id,
        user_message_id=message_id,
        result=RetrievalResult(
            chunks=[
                RetrievedChunk(
                    content="State belongs to a component.",
                    metadata={
                        "chunk_id": str(chunk_id),
                        "document_id": str(document_id),
                        "source_type": "course_repo",
                        "source_path": "src/content/en/state.md",
                        "title": "State",
                        "score": 0.8,
                    },
                    distance=0.2,
                    similarity=0.8,
                )
            ]
        ),
    )

    assert record.query_text == "What is state?"
    assert record.conversation_id == conversation_id
    assert record.user_message_id == message_id
    assert record.chunks[0].chunk_id == str(chunk_id)
    assert record.chunks[0].document_id == str(document_id)
    assert record.chunks[0].rank == 1
    assert record.chunks[0].source_path == "src/content/en/state.md"
    assert record.chunks[0].distance == 0.2
    assert record.chunks[0].similarity == 0.8


@pytest.mark.asyncio
async def test_postgres_rag_trace_sink_persists_typed_retrieval_record() -> None:
    session_factory = FakeSessionFactory()
    repository = CapturingRepository()
    sink = PostgresRagTraceSink(
        rag_index_version="fso-2026-06",
        session_factory=session_factory,
        repository=repository,
    )
    conversation_id = uuid4()
    message_id = uuid4()
    chunk_id = uuid4()

    await sink.record_retrieval(
        {
            "rag_retrieval": RagRetrievalLogRecord(
                query_text="What is state?",
                conversation_id=conversation_id,
                user_message_id=message_id,
                chunks=[
                    {
                        "chunk_id": chunk_id,
                        "distance": 0.2,
                        "similarity": 0.8,
                    }
                ],
            )
        }
    )

    assert repository.call == {
        "query_text": "What is state?",
        "retrieved_chunk_ids": [str(chunk_id)],
        "scores": [
            {
                "chunk_id": str(chunk_id),
                "distance": 0.2,
                "similarity": 0.8,
            }
        ],
        "conversation_id": conversation_id,
        "message_id": message_id,
        "rag_index_version": "fso-2026-06",
    }
    assert session_factory.session.commit_count == 1


@pytest.mark.asyncio
async def test_postgres_rag_trace_sink_failure_does_not_escape() -> None:
    session_factory = FakeSessionFactory()
    sink = PostgresRagTraceSink(
        session_factory=session_factory,
        repository=CapturingRepository(error=RuntimeError("database unavailable")),
    )

    await sink.record_retrieval(
        {
            "rag_retrieval": RagRetrievalLogRecord(
                query_text="What is state?",
                conversation_id=uuid4(),
                user_message_id=uuid4(),
            )
        }
    )

    assert session_factory.session.commit_count == 0


class FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0

    async def commit(self) -> None:
        self.commit_count += 1


class FakeSessionFactory:
    def __init__(self) -> None:
        self.session = FakeSession()

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class CapturingRepository:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.call = None

    async def write_retrieval_log(self, session, **kwargs):
        if self.error is not None:
            raise self.error
        self.call = kwargs
        return object()
