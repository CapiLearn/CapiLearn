from uuid import uuid4

import pytest

from backend.rag.models import EMBEDDING_DIMENSIONS
from backend.rag.repository import ChunkRecord, EmbeddingRecord, SimilarChunk
from backend.rag.service import RagService


@pytest.mark.asyncio
async def test_insert_embeddings_rejects_wrong_dimension_without_writing() -> None:
    session = FakeSession()
    repository = CapturingRepository()
    service = RagService(session=session, repository=repository)

    with pytest.raises(ValueError, match="exactly 384 dimensions"):
        await service.insert_embeddings(
            embeddings=[
                EmbeddingRecord(
                    chunk_id=uuid4(),
                    embedding=[0.1, 0.2],
                    embedding_model="sentence-transformers/all-MiniLM-L6-v2",
                )
            ]
        )

    assert repository.inserted_embeddings is None
    assert session.commit_count == 0


@pytest.mark.asyncio
async def test_insert_embeddings_writes_and_commits_valid_vectors() -> None:
    session = FakeSession()
    repository = CapturingRepository()
    service = RagService(session=session, repository=repository)
    records = [
        EmbeddingRecord(
            chunk_id=uuid4(),
            embedding=[0.0] * EMBEDDING_DIMENSIONS,
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        )
    ]

    rows = await service.insert_embeddings(embeddings=records)

    assert rows == ["embedding-row"]
    assert repository.inserted_embeddings == records
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_retrieve_returns_results_and_optionally_writes_log() -> None:
    session = FakeSession()
    result = SimilarChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        content="Course content",
        metadata={"week": "2"},
        source_type="course_repo",
        source_path="src/content/en/example.md",
        title="Example",
        course_name="Full Stack Open",
        distance=0.2,
        similarity=0.8,
    )
    repository = CapturingRepository(results=[result])
    service = RagService(session=session, repository=repository)

    results = await service.retrieve(
        query_text="What is state?",
        query_embedding=[0.0] * EMBEDDING_DIMENSIONS,
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        top_k=4,
        write_log=True,
        conversation_id=uuid4(),
        message_id=uuid4(),
        rag_index_version="fso-2026-06",
    )

    assert results == [result]
    assert repository.search_top_k == 4
    assert repository.logged_results == [result]
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_replace_document_index_writes_atomically() -> None:
    session = FakeSession()
    repository = CapturingRepository()
    service = RagService(session=session, repository=repository)
    chunk_id = uuid4()
    chunks = [ChunkRecord(id=chunk_id, chunk_index=0, content="Course content")]
    embeddings = [
        EmbeddingRecord(
            chunk_id=chunk_id,
            embedding=[0.0] * EMBEDDING_DIMENSIONS,
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        )
    ]

    document = await service.replace_document_index(
        source_type="course_repo",
        source_path="src/content/en/example.md",
        content_hash="content-hash",
        chunks=chunks,
        embeddings=embeddings,
    )

    assert document == repository.document
    assert repository.deleted_document_id == repository.document.id
    assert repository.inserted_chunks == chunks
    assert repository.inserted_embeddings == embeddings
    assert session.commit_count == 1
    assert session.rollback_count == 0


@pytest.mark.asyncio
async def test_replace_document_index_rolls_back_on_failure() -> None:
    session = FakeSession()
    repository = CapturingRepository(error=RuntimeError("insert failed"))
    service = RagService(session=session, repository=repository)
    chunk_id = uuid4()

    with pytest.raises(RuntimeError, match="insert failed"):
        await service.replace_document_index(
            source_type="course_repo",
            source_path="src/content/en/example.md",
            content_hash="content-hash",
            chunks=[ChunkRecord(id=chunk_id, chunk_index=0, content="Course content")],
            embeddings=[
                EmbeddingRecord(
                    chunk_id=chunk_id,
                    embedding=[0.0] * EMBEDDING_DIMENSIONS,
                    embedding_model="sentence-transformers/all-MiniLM-L6-v2",
                )
            ],
        )

    assert session.commit_count == 0
    assert session.rollback_count == 1


class FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.rollback_count = 0

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1


class CapturingRepository:
    def __init__(self, *, results=None, error: Exception | None = None) -> None:
        self.results = results or []
        self.error = error
        self.document = FakeDocument()
        self.inserted_embeddings = None
        self.inserted_chunks = None
        self.deleted_document_id = None
        self.search_top_k = None
        self.logged_results = None

    async def insert_embeddings(self, session, *, embeddings):
        if self.error is not None:
            raise self.error
        self.inserted_embeddings = embeddings
        return ["embedding-row"]

    async def upsert_document(self, session, **kwargs):
        return self.document

    async def delete_chunks(self, session, *, document_id):
        self.deleted_document_id = document_id

    async def insert_chunks(self, session, *, document_id, chunks):
        self.inserted_chunks = chunks
        return chunks

    async def find_similar_chunks(
        self,
        session,
        *,
        query_embedding,
        embedding_model,
        top_k,
    ):
        self.search_top_k = top_k
        return self.results

    async def write_retrieval_log(
        self,
        session,
        *,
        query_text,
        results,
        conversation_id,
        message_id,
        rag_index_version,
    ):
        self.logged_results = results
        return object()


class FakeDocument:
    def __init__(self) -> None:
        self.id = uuid4()
