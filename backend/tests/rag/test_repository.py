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


def test_rag_document_source_identity_is_unique() -> None:
    constraint_names = {constraint.name for constraint in RagDocument.__table__.constraints}

    assert "rag_documents_source_type_source_path_key" in constraint_names


@pytest.mark.asyncio
async def test_upsert_document_inserts_with_atomic_conflict_handling() -> None:
    document = RagDocument(
        source_type="course_repo",
        source_path="src/content/en/state.md",
        content_hash="new-hash",
        title="State",
        course_name="Full Stack Open",
        extra_metadata={"week": "1"},
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
    sql = _compiled_sql(session.statements[0])
    assert "INSERT INTO rag_documents" in sql
    assert "ON CONFLICT (source_type, source_path) DO UPDATE SET" in sql
    assert "RETURNING rag_documents.id" in sql
    assert "SELECT" not in sql


@pytest.mark.asyncio
async def test_upsert_document_updates_mutable_fields_for_existing_source() -> None:
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
    sql = _compiled_sql(session.statements[0])
    assert "title = " in sql
    assert "course_name = " in sql
    assert "content_hash = " in sql
    assert "metadata = " in sql
    assert "updated_at = " in sql
    assert "source_type = " not in sql.split("DO UPDATE SET", 1)[1]
    assert "source_path = " not in sql.split("DO UPDATE SET", 1)[1]


@pytest.mark.asyncio
async def test_upsert_document_reuses_source_identity_without_duplicate_rows() -> None:
    document = RagDocument(
        source_type="course_repo",
        source_path="src/content/en/state.md",
        content_hash="old-hash",
        extra_metadata={},
    )
    session = UpsertSession(document=document)
    repository = RagRepository()

    first = await repository.upsert_document(
        session,
        source_type=document.source_type,
        source_path=document.source_path,
        content_hash="first-hash",
    )
    second = await repository.upsert_document(
        session,
        source_type=document.source_type,
        source_path=document.source_path,
        content_hash="second-hash",
    )

    assert first is second is document
    assert len(session.rows) == 1
    assert all("ON CONFLICT" in _compiled_sql(statement) for statement in session.statements)


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
        self.rows = (
            {(document.source_type, document.source_path): document} if document is not None else {}
        )
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return ScalarResult(self.document)


class FakeResult:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def all(self) -> list[tuple]:
        return self._rows


class ScalarResult:
    def __init__(self, value) -> None:
        self._value = value

    def scalar_one(self):
        return self._value


def _compiled_sql(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": False},
        )
    )
