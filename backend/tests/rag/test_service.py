from uuid import uuid4

import pytest

from backend.rag.defaults import DEFAULT_RAG_EMBEDDING_PROVIDER, DEFAULT_RAG_MODEL_NAME
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
                    embedding_provider=DEFAULT_RAG_EMBEDDING_PROVIDER,
                    embedding_model=DEFAULT_RAG_MODEL_NAME,
                    embedding_dimensions=EMBEDDING_DIMENSIONS,
                )
            ]
        )

    assert repository.inserted_embeddings is None
    assert session.commit_count == 0


@pytest.mark.asyncio
async def test_insert_embeddings_rejects_wrong_provider_without_writing() -> None:
    session = FakeSession()
    repository = CapturingRepository()
    service = RagService(session=session, repository=repository)

    with pytest.raises(ValueError, match="RAG_EMBEDDING_PROVIDER"):
        await service.insert_embeddings(
            embeddings=[
                EmbeddingRecord(
                    chunk_id=uuid4(),
                    embedding=[0.0] * EMBEDDING_DIMENSIONS,
                    embedding_provider="sentence-transformers",
                    embedding_model=DEFAULT_RAG_MODEL_NAME,
                    embedding_dimensions=EMBEDDING_DIMENSIONS,
                )
            ]
        )

    assert repository.inserted_embeddings is None
    assert session.commit_count == 0


@pytest.mark.asyncio
async def test_insert_embeddings_rejects_wrong_model_without_writing() -> None:
    session = FakeSession()
    repository = CapturingRepository()
    service = RagService(session=session, repository=repository)

    with pytest.raises(ValueError, match="RAG_MODEL_NAME"):
        await service.insert_embeddings(
            embeddings=[
                EmbeddingRecord(
                    chunk_id=uuid4(),
                    embedding=[0.0] * EMBEDDING_DIMENSIONS,
                    embedding_provider=DEFAULT_RAG_EMBEDDING_PROVIDER,
                    embedding_model="text-embedding-ada-002",
                    embedding_dimensions=EMBEDDING_DIMENSIONS,
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
            embedding_provider=DEFAULT_RAG_EMBEDDING_PROVIDER,
            embedding_model=DEFAULT_RAG_MODEL_NAME,
            embedding_dimensions=EMBEDDING_DIMENSIONS,
        )
    ]

    rows = await service.insert_embeddings(embeddings=records)

    assert rows == ["embedding-row"]
    assert repository.inserted_embeddings == records
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_retrieve_returns_results_without_logging_side_effects() -> None:
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
        query_embedding=[0.0] * EMBEDDING_DIMENSIONS,
        embedding_provider=DEFAULT_RAG_EMBEDDING_PROVIDER,
        embedding_model=DEFAULT_RAG_MODEL_NAME,
        embedding_dimensions=EMBEDDING_DIMENSIONS,
        top_k=4,
    )

    assert results == [result]
    assert repository.search_embedding_provider == DEFAULT_RAG_EMBEDDING_PROVIDER
    assert repository.search_top_k == 4
    assert session.commit_count == 0


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
            embedding_provider=DEFAULT_RAG_EMBEDDING_PROVIDER,
            embedding_model=DEFAULT_RAG_MODEL_NAME,
            embedding_dimensions=EMBEDDING_DIMENSIONS,
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
                    embedding_provider=DEFAULT_RAG_EMBEDDING_PROVIDER,
                    embedding_model=DEFAULT_RAG_MODEL_NAME,
                    embedding_dimensions=EMBEDDING_DIMENSIONS,
                )
            ],
        )

    assert session.commit_count == 0
    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_replace_document_index_rejects_duplicate_chunk_indexes() -> None:
    session = FakeSession()
    repository = CapturingRepository()
    service = RagService(session=session, repository=repository)
    first_id = uuid4()
    second_id = uuid4()

    with pytest.raises(ValueError, match="Chunk indexes must be unique"):
        await service.replace_document_index(
            source_type="course_repo",
            source_path="src/content/en/example.md",
            content_hash="content-hash",
            chunks=[
                ChunkRecord(id=first_id, chunk_index=0, content="First"),
                ChunkRecord(id=second_id, chunk_index=0, content="Second"),
            ],
            embeddings=[
                EmbeddingRecord(
                    chunk_id=first_id,
                    embedding=[0.0] * EMBEDDING_DIMENSIONS,
                    embedding_provider=DEFAULT_RAG_EMBEDDING_PROVIDER,
                    embedding_model=DEFAULT_RAG_MODEL_NAME,
                    embedding_dimensions=EMBEDDING_DIMENSIONS,
                ),
                EmbeddingRecord(
                    chunk_id=second_id,
                    embedding=[0.0] * EMBEDDING_DIMENSIONS,
                    embedding_provider=DEFAULT_RAG_EMBEDDING_PROVIDER,
                    embedding_model=DEFAULT_RAG_MODEL_NAME,
                    embedding_dimensions=EMBEDDING_DIMENSIONS,
                ),
            ],
        )

    assert repository.deleted_document_id is None
    assert session.commit_count == 0


@pytest.mark.asyncio
async def test_reconcile_documents_commits_soft_deactivation() -> None:
    session = FakeSession()
    repository = CapturingRepository()
    repository.deactivated_count = 2
    service = RagService(session=session, repository=repository)

    count = await service.reconcile_documents(
        source_type="course_repo",
        course_name="Full Stack Open",
        seen_source_paths=["active.md"],
    )

    assert count == 2
    assert repository.reconciliation == {
        "source_type": "course_repo",
        "course_name": "Full Stack Open",
        "seen_source_paths": ["active.md"],
    }
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_reconcile_documents_rejects_empty_scan_without_writing() -> None:
    session = FakeSession()
    repository = CapturingRepository()
    service = RagService(session=session, repository=repository)

    with pytest.raises(ValueError, match="must not be empty"):
        await service.reconcile_documents(
            source_type="course_repo",
            course_name="Full Stack Open",
            seen_source_paths=[],
        )

    assert repository.reconciliation is None
    assert session.commit_count == 0


@pytest.mark.asyncio
async def test_deactivate_documents_by_source_paths_commits_soft_deactivation() -> None:
    session = FakeSession()
    repository = CapturingRepository()
    repository.deactivated_count = 2
    service = RagService(session=session, repository=repository)

    count = await service.deactivate_documents_by_source_paths(
        source_type="course_repo",
        source_paths=["empty.md", "excluded.md"],
    )

    assert count == 2
    assert repository.targeted_deactivation == {
        "source_type": "course_repo",
        "source_paths": ["empty.md", "excluded.md"],
    }
    assert session.commit_count == 1
    assert session.rollback_count == 0


@pytest.mark.asyncio
async def test_deactivate_documents_by_source_paths_rolls_back_on_failure() -> None:
    session = FakeSession()
    repository = CapturingRepository(error=RuntimeError("update failed"))
    service = RagService(session=session, repository=repository)

    with pytest.raises(RuntimeError, match="update failed"):
        await service.deactivate_documents_by_source_paths(
            source_type="course_repo",
            source_paths=["empty.md"],
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
        self.search_query_embedding = None
        self.search_embedding_provider = None
        self.search_embedding_model = None
        self.search_embedding_dimensions = None
        self.search_top_k = None
        self.deactivated_count = 0
        self.reconciliation = None
        self.targeted_deactivation = None

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
        embedding_provider,
        embedding_model,
        embedding_dimensions,
        top_k,
    ):
        self.search_query_embedding = query_embedding
        self.search_embedding_provider = embedding_provider
        self.search_embedding_model = embedding_model
        self.search_embedding_dimensions = embedding_dimensions
        self.search_top_k = top_k
        return self.results

    async def deactivate_missing_documents(
        self,
        session,
        *,
        source_type,
        course_name,
        seen_source_paths,
    ):
        self.reconciliation = {
            "source_type": source_type,
            "course_name": course_name,
            "seen_source_paths": seen_source_paths,
        }
        return self.deactivated_count

    async def deactivate_documents_by_source_paths(
        self,
        session,
        *,
        source_type,
        source_paths,
    ):
        if self.error is not None:
            raise self.error
        self.targeted_deactivation = {
            "source_type": source_type,
            "source_paths": source_paths,
        }
        return self.deactivated_count


class FakeDocument:
    def __init__(self) -> None:
        self.id = uuid4()
