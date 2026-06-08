from pathlib import Path
from uuid import UUID

import pytest

from backend.ingestion.ingest_pgvector import IngestionConfig, ingest_corpus, prepare_corpus
from backend.rag.models import EMBEDDING_DIMENSIONS


def test_prepare_corpus_reuses_english_filter_and_chunking(tmp_path: Path) -> None:
    _write(tmp_path / "src/content/1/en/part1.md", "# State\n\n" + ("A" * 1200))
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
    assert [chunk["chunk_index"] for chunk in prepared[0].chunks] == [0, 1]


@pytest.mark.asyncio
async def test_dry_run_does_not_load_model_or_open_database(tmp_path: Path) -> None:
    _write(tmp_path / "src/content/1/en/part1.md", "# State\n\nCourse content")

    summary = await ingest_corpus(
        IngestionConfig(repo_path=tmp_path, dry_run=True),
        model_factory=lambda name: (_ for _ in ()).throw(AssertionError("model loaded")),
        session_factory=lambda: (_ for _ in ()).throw(AssertionError("database opened")),
    )

    assert summary.prepared_documents == 1
    assert summary.prepared_chunks == 1
    assert summary.documents_written == 0


@pytest.mark.asyncio
async def test_ingest_corpus_embeds_and_replaces_each_document(tmp_path: Path) -> None:
    _write(tmp_path / "src/content/1/en/part1.md", "# State\n\nCourse content")
    service = CapturingService()

    summary = await ingest_corpus(
        IngestionConfig(repo_path=tmp_path),
        model_factory=lambda name: FakeEmbeddingModel(),
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
    assert len(call["embeddings"][0].embedding) == EMBEDDING_DIMENSIONS


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class FakeEmbeddingModel:
    def get_sentence_embedding_dimension(self) -> int:
        return EMBEDDING_DIMENSIONS

    def encode(self, sentences, *, batch_size, show_progress_bar):
        return [[0.0] * EMBEDDING_DIMENSIONS for _ in sentences]


class FakeSessionFactory:
    def __init__(self) -> None:
        self.session = object()

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class CapturingService:
    def __init__(self) -> None:
        self.calls = []

    async def replace_document_index(self, **kwargs):
        self.calls.append(kwargs)
        return object()
