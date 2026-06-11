from pathlib import Path
from uuid import UUID

import pytest

from backend.ingestion.ingest_pgvector import (
    IngestionConfig,
    build_ingestion_config,
    build_parser,
    ingest_corpus,
    prepare_corpus,
    run_ingestion_preflight,
)
from backend.rag.config import RagBackend, RagEmbeddingProvider, RagSettings
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
        embedding_provider=FailingEmbeddingProvider(),
        session_factory=lambda: (_ for _ in ()).throw(AssertionError("database opened")),
    )

    assert summary.prepared_documents == 1
    assert summary.prepared_chunks == 1
    assert summary.documents_written == 0
    assert summary.documents_deactivated == 0


@pytest.mark.asyncio
async def test_empty_corpus_fails_before_database_or_provider_use(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="contains no supported files"):
        await ingest_corpus(
            IngestionConfig(repo_path=tmp_path, reconcile_deletions=True),
            embedding_provider=FailingEmbeddingProvider(),
            session_factory=lambda: (_ for _ in ()).throw(AssertionError("database opened")),
        )


@pytest.mark.asyncio
async def test_ingestion_rejects_unsupported_pgvector_dimensions_before_loading_provider(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="current database schema stores vector\\(384\\)"):
        await ingest_corpus(
            IngestionConfig(
                repo_path=tmp_path,
                embedding_dimensions=1536,
                dry_run=True,
            ),
            embedding_provider=FailingEmbeddingProvider(),
        )


def test_cli_overrides_reject_crossed_provider_and_model() -> None:
    settings = RagSettings(
        _env_file=None,
        embedding_provider=RagEmbeddingProvider.OPENAI,
        model_name="text-embedding-3-small",
        OPENAI_API_KEY="test-key",
    )
    args = build_parser(settings).parse_args(
        [
            "--embedding-provider",
            "openai",
            "--model-name",
            "sentence-transformers/all-MiniLM-L6-v2",
        ]
    )

    with pytest.raises(ValueError, match="must be 'text-embedding-3-small'"):
        build_ingestion_config(args, settings)


def test_cli_overrides_reject_openai_model_for_sentence_transformers() -> None:
    settings = RagSettings(_env_file=None)
    args = build_parser(settings).parse_args(
        [
            "--embedding-provider",
            "sentence_transformers",
            "--model-name",
            "text-embedding-3-small",
        ]
    )

    with pytest.raises(ValueError, match="all-MiniLM-L6-v2"):
        build_ingestion_config(args, settings)


def test_preflight_rejects_missing_corpus_path(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing"

    with pytest.raises(FileNotFoundError, match="backend.ingestion.fetch_corpus"):
        run_ingestion_preflight(
            IngestionConfig(repo_path=missing_path),
            require_database_url=False,
        )


def test_preflight_rejects_corpus_without_english_sources(tmp_path: Path) -> None:
    _write(tmp_path / "src/content/1/es/part1.md", "# Estado")

    with pytest.raises(ValueError, match="no non-empty English course files"):
        run_ingestion_preflight(
            IngestionConfig(repo_path=tmp_path),
            require_database_url=False,
        )


def test_preflight_accepts_fixture_corpus_and_valid_contract(tmp_path: Path) -> None:
    _write(tmp_path / "src/content/1/en/part1.md", "# State")
    config = IngestionConfig(
        repo_path=tmp_path,
        backend=RagBackend.PGVECTOR,
        database_url="postgresql+asyncpg://user:password@host/capilearn",
    )

    result = run_ingestion_preflight(config, require_database_url=True)

    assert result.corpus_path == tmp_path.resolve()
    assert result.supported_files == 1
    assert result.nonempty_english_files == 1


def test_preflight_requires_database_url_for_ingestion(tmp_path: Path) -> None:
    _write(tmp_path / "src/content/1/en/part1.md", "# State")

    with pytest.raises(ValueError, match="DATABASE_URL is required"):
        run_ingestion_preflight(
            IngestionConfig(repo_path=tmp_path, database_url=""),
            require_database_url=True,
        )


def test_corpus_source_path_setting_is_used_by_parser(tmp_path: Path) -> None:
    settings = RagSettings(_env_file=None, corpus_source_path=tmp_path)

    args = build_parser(settings).parse_args([])

    assert args.repo_path == tmp_path


@pytest.mark.asyncio
async def test_ingest_corpus_embeds_and_replaces_each_document(tmp_path: Path) -> None:
    _write(tmp_path / "src/content/1/en/part1.md", "# State\n\nCourse content")
    service = CapturingService()

    summary = await ingest_corpus(
        IngestionConfig(repo_path=tmp_path),
        embedding_provider=FakeEmbeddingProvider(),
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


@pytest.mark.asyncio
async def test_reconciliation_is_opt_in_and_uses_seen_english_paths(tmp_path: Path) -> None:
    _write(tmp_path / "src/content/1/en/part1.md", "# State\n\nCourse content")
    _write(tmp_path / "src/content/1/en/empty.md", "")
    _write(tmp_path / "src/content/1/es/part1.md", "# Estado\n\nContenido")
    service = CapturingService(deactivated=2)

    summary = await ingest_corpus(
        IngestionConfig(repo_path=tmp_path, reconcile_deletions=True),
        embedding_provider=FakeEmbeddingProvider(),
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
        embedding_provider=FakeEmbeddingProvider(),
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
        embedding_provider=FakeEmbeddingProvider(),
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
        embedding_provider=FakeEmbeddingProvider(),
        session_factory=FakeSessionFactory,
        service_factory=lambda *, session: service,
    )

    assert summary.preprocessing_failures == 1
    assert service.reconciliation_calls == []


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class FakeEmbeddingProvider:
    provider_name = "fake"
    model_name = "fake-model"
    dimensions = EMBEDDING_DIMENSIONS

    def embed_text(self, text: str) -> list[float]:
        return [0.0] * EMBEDDING_DIMENSIONS

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]


class FailingEmbeddingProvider(FakeEmbeddingProvider):
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise AssertionError("embedding provider used")


class FakeSessionFactory:
    def __init__(self) -> None:
        self.session = object()

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class CapturingService:
    def __init__(
        self,
        *,
        deactivated: int = 0,
        fail_path: str | None = None,
    ) -> None:
        self.calls = []
        self.reconciliation_calls = []
        self.deactivated = deactivated
        self.fail_path = fail_path

    async def replace_document_index(self, **kwargs):
        if kwargs["source_path"] == self.fail_path:
            raise RuntimeError("database unavailable")
        self.calls.append(kwargs)
        return object()

    async def reconcile_documents(self, **kwargs):
        self.reconciliation_calls.append(kwargs)
        return self.deactivated
