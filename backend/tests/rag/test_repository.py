from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from backend.rag.defaults import DEFAULT_RAG_EMBEDDING_PROVIDER, DEFAULT_RAG_MODEL_NAME
from backend.rag.models import EMBEDDING_DIMENSIONS, RagChunk, RagDocument, RagEmbedding
from backend.rag.repository import ChunkRecord, EmbeddingRecord, RagRepository, SimilarChunk


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
    assert RagDocument.__table__.c.is_active.default.arg is True


def test_rag_chunk_and_embedding_identity_constraints_are_unique() -> None:
    chunk_constraints = {constraint.name for constraint in RagChunk.__table__.constraints}
    embedding_constraints = {constraint.name for constraint in RagEmbedding.__table__.constraints}

    assert "rag_chunks_document_id_chunk_index_key" in chunk_constraints
    assert "rag_embeddings_chunk_id_embedding_contract_key" in embedding_constraints
    assert "embedding_provider" in RagEmbedding.__table__.c
    assert "embedding_dimensions" in RagEmbedding.__table__.c


@pytest.mark.asyncio
async def test_insert_embeddings_maps_full_contract_to_model() -> None:
    session = InsertSession()
    chunk_id = uuid4()
    record = EmbeddingRecord(
        chunk_id=chunk_id,
        embedding=[0.0] * EMBEDDING_DIMENSIONS,
        embedding_provider=DEFAULT_RAG_EMBEDDING_PROVIDER,
        embedding_model=DEFAULT_RAG_MODEL_NAME,
        embedding_dimensions=EMBEDDING_DIMENSIONS,
    )

    rows = await RagRepository().insert_embeddings(
        session,
        embeddings=[record],
    )

    assert rows[0].chunk_id == chunk_id
    assert rows[0].embedding_provider == DEFAULT_RAG_EMBEDDING_PROVIDER
    assert rows[0].embedding_model == DEFAULT_RAG_MODEL_NAME
    assert rows[0].embedding_dimensions == EMBEDDING_DIMENSIONS


@pytest.mark.asyncio
async def test_insert_chunks_maps_contract_fields_to_model() -> None:
    session = InsertSession()
    document_id = uuid4()
    record = ChunkRecord(
        id=uuid4(),
        chunk_index=0,
        content="# State\n\nCourse content",
        content_hash="abc123",
        char_start=0,
        char_end=23,
        heading_path=("State",),
        section_heading="State",
        chunk_type="unknown",
        chunker_version="markdown-window-v2-contract",
        metadata={"source_path": "state.md"},
    )

    rows = await RagRepository().insert_chunks(
        session,
        document_id=document_id,
        chunks=[record],
    )

    assert rows[0].document_id == document_id
    assert rows[0].content_hash == "abc123"
    assert rows[0].char_start == 0
    assert rows[0].char_end == 23
    assert rows[0].heading_path == ["State"]
    assert rows[0].section_heading == "State"
    assert rows[0].chunk_type == "unknown"
    assert rows[0].chunker_version == "markdown-window-v2-contract"


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
    assert "is_active = " in sql
    assert "deleted_at = " in sql
    assert "updated_at = " in sql
    assert "source_type = " not in sql.split("DO UPDATE SET", 1)[1]
    assert "source_path = " not in sql.split("DO UPDATE SET", 1)[1]


@pytest.mark.asyncio
async def test_upsert_document_reactivates_reappearing_source() -> None:
    document = RagDocument(
        source_type="course_repo",
        source_path="src/content/en/state.md",
        content_hash="old-hash",
        is_active=False,
        deleted_at=None,
        extra_metadata={},
    )
    session = UpsertSession(document=document)

    await RagRepository().upsert_document(
        session,
        source_type=document.source_type,
        source_path=document.source_path,
        content_hash="new-hash",
    )

    update_sql = _compiled_sql(session.statements[0]).split("DO UPDATE SET", 1)[1]
    assert "is_active = " in update_sql
    assert "deleted_at = " in update_sql


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
                "chunk-hash",
                10,
                45,
                ["State"],
                "State",
                "prose",
                "markdown-window-v2-contract",
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
        embedding_provider=DEFAULT_RAG_EMBEDDING_PROVIDER,
        embedding_model=DEFAULT_RAG_MODEL_NAME,
        embedding_dimensions=EMBEDDING_DIMENSIONS,
        top_k=3,
    )

    sql = str(
        session.statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": False},
        )
    )
    assert "rag_embeddings.embedding <=>" in sql
    assert "rag_embeddings.embedding_provider" in sql
    assert "rag_embeddings.embedding_model" in sql
    assert "rag_embeddings.embedding_dimensions" in sql
    assert "rag_documents.is_active IS true" in sql
    assert "LIMIT" in sql
    assert results == [
        SimilarChunk(
            chunk_id=chunk_id,
            document_id=document_id,
            content="React state stores component data.",
            metadata={
                "week": "1",
                "content_hash": "chunk-hash",
                "char_start": 10,
                "char_end": 45,
                "heading_path": ["State"],
                "section_heading": "State",
                "chunk_type": "prose",
                "chunker_version": "markdown-window-v2-contract",
            },
            source_type="course_repo",
            source_path="src/content/en/state.md",
            title="State",
            course_name="Full Stack Open",
            distance=0.125,
            similarity=0.875,
        )
    ]


@pytest.mark.asyncio
async def test_deactivate_missing_documents_soft_deletes_only_unseen_active_sources() -> None:
    session = RowCountSession(rowcount=2)

    count = await RagRepository().deactivate_missing_documents(
        session,
        source_type="course_repo",
        course_name="Full Stack Open",
        seen_source_paths=["active.md"],
    )

    sql = _compiled_sql(session.statement)
    assert count == 2
    assert "UPDATE rag_documents" in sql
    assert "rag_documents.is_active IS true" in sql
    assert "rag_documents.course_name =" in sql
    assert "rag_documents.source_path NOT IN" in sql
    assert "is_active=" in sql
    assert "deleted_at=" in sql
    assert "DELETE" not in sql


@pytest.mark.asyncio
async def test_deactivate_missing_documents_rejects_empty_scan() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        await RagRepository().deactivate_missing_documents(
            RowCountSession(rowcount=0),
            source_type="course_repo",
            course_name="Full Stack Open",
            seen_source_paths=[],
        )


@pytest.mark.asyncio
async def test_deactivate_documents_by_source_paths_uses_document_identity() -> None:
    session = RowCountSession(rowcount=2)

    count = await RagRepository().deactivate_documents_by_source_paths(
        session,
        source_type="course_repo",
        source_paths=["empty.md", "excluded.md"],
    )

    sql = _compiled_sql(session.statement)
    assert count == 2
    assert "UPDATE rag_documents" in sql
    assert "rag_documents.source_type =" in sql
    assert "rag_documents.course_name" not in sql
    assert "rag_documents.is_active IS true" in sql
    assert "rag_documents.source_path IN" in sql
    assert "DELETE" not in sql


@pytest.mark.asyncio
async def test_deactivate_documents_by_source_paths_rejects_empty_paths() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        await RagRepository().deactivate_documents_by_source_paths(
            RowCountSession(rowcount=0),
            source_type="course_repo",
            source_paths=[],
        )


class CapturingSession:
    def __init__(self, *, rows: list[tuple]) -> None:
        self.statement = None
        self._rows = rows

    async def execute(self, statement):
        self.statement = statement
        return FakeResult(self._rows)


class RowCountSession:
    def __init__(self, *, rowcount: int) -> None:
        self.rowcount = rowcount
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return RowCountResult(self.rowcount)


class InsertSession:
    def __init__(self) -> None:
        self.rows = []

    def add_all(self, rows) -> None:
        self.rows.extend(rows)

    async def flush(self) -> None:
        return None


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


class RowCountResult:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


def _compiled_sql(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": False},
        )
    )
