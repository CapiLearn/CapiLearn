from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy.sql.elements import TextClause

import backend.ingestion.ingest_pgvector as ingestion_module
from backend.ingestion.ingest_pgvector import IngestionConfig, ingest_corpus, prepare_corpus
from backend.rag.chunking import PreparedChunk
from backend.rag.defaults import DEFAULT_RAG_EMBEDDING_PROVIDER, DEFAULT_RAG_MODEL_NAME
from backend.rag.models import EMBEDDING_DIMENSIONS


def test_prepare_corpus_reuses_english_filter_and_chunking(tmp_path: Path) -> None:
    content = "# State\n\n" + ("First paragraph. " * 40) + "\n\n" + ("Second paragraph. " * 40)
    _write(tmp_path / "src/content/1/en/part1.md", content)
    _write(tmp_path / "src/content/1/es/part1.md", "# Estado\n\nContenido")
    _write(tmp_path / "src/content/2/en/empty.md", "")

    prepared, summary = prepare_corpus(
        IngestionConfig(
            repo_path=tmp_path,
            chunk_size=1000,
            chunk_overlap=200,
            dry_run=True,
        )
    )

    assert summary.discovered_files == 3
    assert summary.prepared_documents == 1
    assert summary.prepared_chunks == 2
    assert summary.skipped_non_english == 1
    assert summary.skipped_empty == 1
    assert prepared[0].source_path == "src/content/1/en/part1.md"
    assert [chunk.chunk_index for chunk in prepared[0].chunks] == [0, 1]
    assert all(chunk.content_hash for chunk in prepared[0].chunks)
    assert all(chunk.chunker_version for chunk in prepared[0].chunks)


@pytest.mark.asyncio
async def test_dry_run_does_not_load_model_or_open_database(tmp_path: Path) -> None:
    _write(tmp_path / "src/content/1/en/part1.md", "# State\n\nCourse content")

    summary = await ingest_corpus(
        IngestionConfig(repo_path=tmp_path, dry_run=True, reconcile_deletions=True),
        model_factory=lambda: (_ for _ in ()).throw(AssertionError("model loaded")),
        session_factory=lambda: (_ for _ in ()).throw(AssertionError("database opened")),
    )

    assert summary.prepared_documents == 1
    assert summary.prepared_chunks == 1
    assert summary.documents_written == 0
    assert summary.documents_deactivated == 0


@pytest.mark.asyncio
async def test_empty_scan_does_not_open_database_or_reconcile(tmp_path: Path) -> None:
    summary = await ingest_corpus(
        IngestionConfig(repo_path=tmp_path, reconcile_deletions=True),
        model_factory=lambda: (_ for _ in ()).throw(AssertionError("model loaded")),
        session_factory=lambda: (_ for _ in ()).throw(AssertionError("database opened")),
    )

    assert summary.prepared_documents == 0
    assert summary.documents_deactivated == 0


@pytest.mark.asyncio
async def test_ingestion_rejects_unsupported_pgvector_model_before_loading_it(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="RAG_MODEL_NAME"):
        await ingest_corpus(
            IngestionConfig(
                repo_path=tmp_path,
                model_name=f"{DEFAULT_RAG_MODEL_NAME}-other",
                dry_run=True,
            ),
            model_factory=lambda: (_ for _ in ()).throw(AssertionError("model loaded")),
        )


@pytest.mark.asyncio
async def test_storage_preflight_failure_prevents_embedding_generation(tmp_path: Path) -> None:
    _write(tmp_path / "src/content/1/en/part1.md", "# State\n\nCourse content")

    async def failing_preflight(*args, **kwargs) -> None:
        raise RuntimeError("rag storage schema is not ready")

    with pytest.raises(RuntimeError, match="storage schema"):
        await ingest_corpus(
            IngestionConfig(repo_path=tmp_path),
            model_factory=lambda: (_ for _ in ()).throw(AssertionError("model loaded")),
            session_factory=FakeSessionFactory,
            storage_preflight=failing_preflight,
        )


@pytest.mark.asyncio
async def test_ingest_corpus_embeds_and_replaces_each_document(tmp_path: Path) -> None:
    _write(tmp_path / "src/content/1/en/part1.md", "# State\n\nCourse content")
    service = CapturingService()

    summary = await ingest_corpus(
        IngestionConfig(repo_path=tmp_path),
        model_factory=lambda: FakeEmbeddingProvider(),
        session_factory=FakeSessionFactory,
        service_factory=lambda *, session: service,
    )

    assert summary.documents_written == 1
    assert summary.chunks_written == 1
    assert summary.embeddings_written == 1
    assert len(service.calls) == 1
    call = service.calls[0]
    assert call["source_path"] == "src/content/1/en/part1.md"
    assert len(call["chunks"]) == 1
    assert isinstance(call["chunks"][0].id, UUID)
    assert call["chunks"][0].content_hash
    assert call["chunks"][0].heading_path == ("State",)
    assert call["chunks"][0].section_heading == "State"
    assert call["chunks"][0].char_start == 0
    assert call["chunks"][0].char_end == len("# State\n\nCourse content")
    assert len(call["embeddings"][0].embedding) == EMBEDDING_DIMENSIONS
    assert call["embeddings"][0].embedding_provider == DEFAULT_RAG_EMBEDDING_PROVIDER
    assert call["embeddings"][0].embedding_model == DEFAULT_RAG_MODEL_NAME
    assert call["embeddings"][0].embedding_dimensions == EMBEDDING_DIMENSIONS


@pytest.mark.asyncio
async def test_ingest_corpus_batches_embeddings_and_preserves_order(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source_path = "src/content/1/en/part1.md"
    _write(tmp_path / source_path, "# State\n\nCourse content")
    chunks = [
        _prepared_chunk(source_path=source_path, chunk_index=index, content=f"chunk {index}")
        for index in range(5)
    ]
    monkeypatch.setattr(ingestion_module, "prepare_chunks", lambda *args, **kwargs: chunks)
    provider = RecordingBatchEmbeddingProvider()
    service = CapturingService()

    summary = await ingest_corpus(
        IngestionConfig(repo_path=tmp_path, embedding_batch_size=2),
        model_factory=lambda: provider,
        session_factory=FakeSessionFactory,
        service_factory=lambda *, session: service,
    )

    assert summary.embeddings_written == 5
    assert provider.calls == [
        ["chunk 0", "chunk 1"],
        ["chunk 2", "chunk 3"],
        ["chunk 4"],
    ]
    assert [record.embedding[0] for record in service.calls[0]["embeddings"]] == [
        0.0,
        1.0,
        2.0,
        3.0,
        4.0,
    ]


@pytest.mark.asyncio
async def test_reconciliation_is_opt_in_and_uses_seen_english_paths(tmp_path: Path) -> None:
    _write(tmp_path / "src/content/1/en/part1.md", "# State\n\nCourse content")
    _write(tmp_path / "src/content/1/en/empty.md", "")
    _write(tmp_path / "src/content/1/es/part1.md", "# Estado\n\nContenido")
    service = CapturingService(deactivated=2)

    summary = await ingest_corpus(
        IngestionConfig(repo_path=tmp_path, reconcile_deletions=True),
        model_factory=lambda: FakeEmbeddingProvider(),
        session_factory=FakeSessionFactory,
        service_factory=lambda *, session: service,
    )

    assert service.reconciliation_calls == [
        {
            "source_type": "course_repo",
            "course_name": "Full Stack Open",
            "seen_source_paths": [
                "src/content/1/en/empty.md",
                "src/content/1/en/part1.md",
                "src/content/1/es/part1.md",
            ],
        }
    ]
    assert service.targeted_deactivation_calls == [
        {
            "source_type": "course_repo",
            "source_paths": [
                "src/content/1/en/empty.md",
                "src/content/1/es/part1.md",
            ],
        }
    ]
    assert summary.documents_deactivated == 2


@pytest.mark.asyncio
async def test_reconciliation_does_not_run_without_opt_in(tmp_path: Path) -> None:
    _write(tmp_path / "src/content/1/en/part1.md", "# State\n\nCourse content")
    service = CapturingService()

    await ingest_corpus(
        IngestionConfig(repo_path=tmp_path),
        model_factory=lambda: FakeEmbeddingProvider(),
        session_factory=FakeSessionFactory,
        service_factory=lambda *, session: service,
    )

    assert service.reconciliation_calls == []


@pytest.mark.asyncio
async def test_partial_database_failure_skips_reconciliation(tmp_path: Path) -> None:
    _write(tmp_path / "src/content/1/en/part1.md", "# State\n\nCourse content")
    _write(tmp_path / "src/content/2/en/part2.md", "# Props\n\nCourse content")
    service = CapturingService(fail_path="src/content/2/en/part2.md")

    summary = await ingest_corpus(
        IngestionConfig(repo_path=tmp_path, reconcile_deletions=True),
        model_factory=lambda: FakeEmbeddingProvider(),
        session_factory=FakeSessionFactory,
        service_factory=lambda *, session: service,
    )

    assert summary.database_failures == 1
    assert service.reconciliation_calls == []


@pytest.mark.asyncio
async def test_preprocessing_failure_skips_reconciliation(tmp_path: Path) -> None:
    _write(tmp_path / "src/content/1/en/part1.md", "# State\n\nCourse content")
    _write(tmp_path / "src/content/2/en/broken.ipynb", "{not-json")
    service = CapturingService()

    summary = await ingest_corpus(
        IngestionConfig(repo_path=tmp_path, reconcile_deletions=True),
        model_factory=lambda: FakeEmbeddingProvider(),
        session_factory=FakeSessionFactory,
        service_factory=lambda *, session: service,
    )

    assert summary.preprocessing_failures == 1
    assert service.reconciliation_calls == []
    assert service.targeted_deactivation_calls == []


@pytest.mark.asyncio
async def test_empty_existing_source_is_targeted_for_deactivation(tmp_path: Path) -> None:
    _write(tmp_path / "src/content/1/en/empty.md", "   \n")
    service = CapturingService(targeted_deactivated=1)

    summary = await ingest_corpus(
        IngestionConfig(repo_path=tmp_path),
        model_factory=lambda: (_ for _ in ()).throw(AssertionError("model loaded")),
        session_factory=FakeSessionFactory,
        service_factory=lambda *, session: service,
    )

    assert service.targeted_deactivation_calls[0]["source_paths"] == ["src/content/1/en/empty.md"]
    assert summary.documents_deactivated == 1


@pytest.mark.asyncio
async def test_zero_chunk_source_is_targeted_for_deactivation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source_path = "src/content/1/en/part1.md"
    _write(tmp_path / source_path, "# State\n\nCourse content")
    monkeypatch.setattr(ingestion_module, "prepare_chunks", lambda *args, **kwargs: [])
    service = CapturingService(targeted_deactivated=1)

    summary = await ingest_corpus(
        IngestionConfig(repo_path=tmp_path),
        model_factory=lambda: (_ for _ in ()).throw(AssertionError("model loaded")),
        session_factory=FakeSessionFactory,
        service_factory=lambda *, session: service,
    )

    assert service.targeted_deactivation_calls[0]["source_paths"] == [source_path]
    assert summary.documents_deactivated == 1


@pytest.mark.asyncio
async def test_excluded_existing_source_is_targeted_for_deactivation(tmp_path: Path) -> None:
    source_path = "src/content/1/es/part1.md"
    _write(tmp_path / source_path, "# Estado\n\nContenido")
    service = CapturingService(targeted_deactivated=1)

    summary = await ingest_corpus(
        IngestionConfig(repo_path=tmp_path),
        model_factory=lambda: (_ for _ in ()).throw(AssertionError("model loaded")),
        session_factory=FakeSessionFactory,
        service_factory=lambda *, session: service,
    )

    assert service.targeted_deactivation_calls[0]["source_paths"] == [source_path]
    assert summary.documents_deactivated == 1


@pytest.mark.asyncio
async def test_preprocessing_failure_is_not_targeted_for_deactivation(tmp_path: Path) -> None:
    _write(tmp_path / "src/content/1/en/broken.ipynb", "{not-json")
    service = CapturingService()

    summary = await ingest_corpus(
        IngestionConfig(repo_path=tmp_path, reconcile_deletions=True),
        model_factory=lambda: (_ for _ in ()).throw(AssertionError("model loaded")),
        session_factory=lambda: (_ for _ in ()).throw(AssertionError("database opened")),
        service_factory=lambda *, session: service,
    )

    assert summary.preprocessing_failures == 1
    assert service.targeted_deactivation_calls == []
    assert service.reconciliation_calls == []


@pytest.mark.asyncio
async def test_ingestion_deactivates_unindexable_sources_without_loading_embedding_model(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "src/content/1/en/empty.md", "")
    service = CapturingService(targeted_deactivated=1)

    summary = await ingest_corpus(
        IngestionConfig(repo_path=tmp_path),
        model_factory=lambda: (_ for _ in ()).throw(AssertionError("model loaded")),
        session_factory=FakeSessionFactory,
        service_factory=lambda *, session: service,
    )

    assert summary.documents_deactivated == 1
    assert service.targeted_deactivation_calls


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _prepared_chunk(
    *,
    source_path: str,
    chunk_index: int,
    content: str,
) -> PreparedChunk:
    return PreparedChunk(
        chunk_id=uuid4(),
        content=content,
        chunk_index=chunk_index,
        source_type="course_repo",
        source_path=source_path,
        heading_path=("State",),
        section_heading="State",
        chunk_type="prose",
        char_start=chunk_index,
        char_end=chunk_index + len(content),
        content_hash=f"hash-{chunk_index}",
        chunker_version="test",
    )


class FakeEmbeddingProvider:
    def embed_documents(self, texts, *, model_name, embedding_dimensions):
        assert model_name == DEFAULT_RAG_MODEL_NAME
        assert embedding_dimensions == EMBEDDING_DIMENSIONS
        return [[0.0] * EMBEDDING_DIMENSIONS for _ in texts]


class RecordingBatchEmbeddingProvider:
    def __init__(self) -> None:
        self.calls = []

    def embed_documents(self, texts, *, model_name, embedding_dimensions):
        assert model_name == DEFAULT_RAG_MODEL_NAME
        assert embedding_dimensions == EMBEDDING_DIMENSIONS
        self.calls.append(list(texts))
        return [
            [float(text.rsplit(" ", 1)[1]), *([0.0] * (EMBEDDING_DIMENSIONS - 1))] for text in texts
        ]


class FakeSessionFactory:
    def __init__(self) -> None:
        self.session = FakeStorageSession()

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class FakeStorageSession:
    async def execute(self, statement, parameters=None):
        sql = _statement_text(statement)
        if "information_schema.columns" in sql:
            rows = [
                (table, column)
                for table, columns in ingestion_module.REQUIRED_RAG_STORAGE_COLUMNS.items()
                for column in columns
            ]
            return FakeResult(rows=rows)
        if "pg_extension" in sql:
            return FakeResult(scalar=True)
        if "format_type" in sql:
            return FakeResult(scalar=f"vector({ingestion_module.DEFAULT_RAG_EMBEDDING_DIMENSIONS})")
        return FakeResult(scalar=1)


class FakeResult:
    def __init__(self, *, rows=None, scalar=None) -> None:
        self._rows = rows or []
        self._scalar = scalar

    def all(self):
        return self._rows

    def scalar_one(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar


def _statement_text(statement) -> str:
    if isinstance(statement, TextClause):
        return statement.text
    return str(statement)


class CapturingService:
    def __init__(
        self,
        *,
        deactivated: int = 0,
        targeted_deactivated: int = 0,
        fail_path: str | None = None,
    ) -> None:
        self.calls = []
        self.reconciliation_calls = []
        self.targeted_deactivation_calls = []
        self.deactivated = deactivated
        self.targeted_deactivated = targeted_deactivated
        self.fail_path = fail_path

    async def replace_document_index(self, **kwargs):
        if kwargs["source_path"] == self.fail_path:
            raise RuntimeError("database unavailable")
        self.calls.append(kwargs)
        return object()

    async def reconcile_documents(self, **kwargs):
        self.reconciliation_calls.append(kwargs)
        return self.deactivated

    async def deactivate_documents_by_source_paths(self, **kwargs):
        self.targeted_deactivation_calls.append(kwargs)
        return self.targeted_deactivated
