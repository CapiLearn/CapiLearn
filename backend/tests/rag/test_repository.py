from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from backend.rag.models import EMBEDDING_DIMENSIONS, RagDocument, RagEmbedding
from backend.rag.repository import RagRepository, SimilarChunk


def test_rag_embedding_uses_384_dimension_vector_and_cosine_index() -> None:
    assert RagEmbedding.__table__.c.embedding.type.dim == EMBEDDING_DIMENSIONS

    index = next(
        index
        for index in RagEmbedding.__table__.indexes
        if index.name == "rag_embeddings_embedding_cosine_idx"
    )
    assert index.dialect_options["postgresql"]["using"] == "hnsw"
    assert index.dialect_options["postgresql"]["ops"] == {"embedding": "vector_cosine_ops"}


@pytest.mark.asyncio
async def test_upsert_document_updates_existing_source() -> None:
    document = RagDocument(
        source_type="course_repo",
        source_path="src/content/en/state.md",
        content_hash="old-hash",
        extra_metadata={},
    )
    session = UpsertSession(document=document)

    result = await RagRepository().upsert_document(
        session,
        source_type="course_repo",
        source_path="src/content/en/state.md",
        content_hash="new-hash",
        title="State",
        course_name="Full Stack Open",
        metadata={"week": "1"},
    )

    assert result is document
    assert document.content_hash == "new-hash"
    assert document.title == "State"
    assert document.course_name == "Full Stack Open"
    assert document.extra_metadata == {"week": "1"}
    assert session.added == []
    assert session.flush_count == 1


@pytest.mark.asyncio
async def test_find_similar_chunks_uses_cosine_distance_and_maps_source_data() -> None:
    chunk_id = uuid4()
    document_id = uuid4()
    session = CapturingSession(
        rows=[
            (
                chunk_id,
                document_id,
                "React state stores component data.",
                {"week": "1"},
                "course_repo",
                "src/content/en/state.md",
                "State",
                "Full Stack Open",
                0.125,
            )
        ]
    )

    results = await RagRepository().find_similar_chunks(
        session,
        query_embedding=[0.0] * EMBEDDING_DIMENSIONS,
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        top_k=3,
    )

    sql = str(
        session.statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": False},
        )
    )
    assert "rag_embeddings.embedding <=>" in sql
    assert "rag_embeddings.embedding_model" in sql
    assert "LIMIT" in sql
    assert results == [
        SimilarChunk(
            chunk_id=chunk_id,
            document_id=document_id,
            content="React state stores component data.",
            metadata={"week": "1"},
            source_type="course_repo",
            source_path="src/content/en/state.md",
            title="State",
            course_name="Full Stack Open",
            distance=0.125,
            similarity=0.875,
        )
    ]
    assert results[0].to_retrieval_dict() == {
        "content": "React state stores component data.",
        "metadata": {
            "week": "1",
            "chunk_id": str(chunk_id),
            "document_id": str(document_id),
            "source_type": "course_repo",
            "source_path": "src/content/en/state.md",
            "title": "State",
            "course_name": "Full Stack Open",
        },
        "distance": 0.125,
        "similarity": 0.875,
    }


class CapturingSession:
    def __init__(self, *, rows: list[tuple]) -> None:
        self.statement = None
        self._rows = rows

    async def execute(self, statement):
        self.statement = statement
        return FakeResult(self._rows)


class UpsertSession:
    def __init__(self, *, document: RagDocument | None) -> None:
        self.document = document
        self.added = []
        self.flush_count = 0

    async def scalar(self, statement):
        return self.document

    def add(self, value) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flush_count += 1


class FakeResult:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def all(self) -> list[tuple]:
        return self._rows
