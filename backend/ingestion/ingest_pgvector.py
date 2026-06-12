from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings as app_settings
from backend.core.database import SessionFactory
from backend.ingestion.ingest_repo import find_course_files, make_document
from backend.rag.chunk_documents import is_english_source
from backend.rag.chunk_identity import content_hash
from backend.rag.chunking import (
    DEFAULT_MAX_OVERSIZED_CODE_CHARS,
    DEFAULT_MIN_CHUNK_CHARS,
    PreparedChunk,
    SourceDocument,
    prepare_chunks,
)
from backend.rag.config import (
    RagBackend,
    RagEmbeddingProvider,
    RagSettings,
    validate_embedding_contract,
)
from backend.rag.defaults import (
    DEFAULT_RAG_EMBEDDING_DIMENSIONS,
    DEFAULT_RAG_EMBEDDING_PROVIDER,
    DEFAULT_RAG_MODEL_NAME,
)
from backend.rag.embeddings import EmbeddingProvider, get_embedding_provider
from backend.rag.repository import ChunkRecord, EmbeddingRecord
from backend.rag.service import RagService

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = DEFAULT_RAG_MODEL_NAME
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 200
DEFAULT_EMBEDDING_BATCH_SIZE = 64
SessionFactoryCallable = Callable[[], AbstractAsyncContextManager[AsyncSession]]
RagServiceFactory = Callable[..., RagService]


@dataclass(frozen=True)
class IngestionConfig:
    repo_path: Path = Path("backend/rag/source_corpus/fullstack_hy2020")
    backend: RagBackend = RagBackend.PGVECTOR
    source_type: str = "course_repo"
    course_name: str = "Full Stack Open"
    embedding_provider: RagEmbeddingProvider = RagEmbeddingProvider(DEFAULT_RAG_EMBEDDING_PROVIDER)
    model_name: str = DEFAULT_MODEL_NAME
    embedding_dimensions: int = DEFAULT_RAG_EMBEDDING_DIMENSIONS
    openai_api_key: str | None = None
    chunk_size: int = DEFAULT_CHUNK_SIZE
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP
    min_chunk_chars: int = DEFAULT_MIN_CHUNK_CHARS
    max_oversized_code_chars: int = DEFAULT_MAX_OVERSIZED_CODE_CHARS
    embedding_batch_size: int = DEFAULT_EMBEDDING_BATCH_SIZE
    dry_run: bool = False
    fail_fast: bool = False
    reconcile_deletions: bool = False


@dataclass(frozen=True)
class PreparedDocument:
    source_path: str
    title: str | None
    content_hash: str
    metadata: dict[str, Any]
    chunks: list[PreparedChunk]


@dataclass
class IngestionSummary:
    discovered_files: int = 0
    prepared_documents: int = 0
    skipped_non_english: int = 0
    skipped_empty: int = 0
    preprocessing_failures: int = 0
    prepared_chunks: int = 0
    documents_written: int = 0
    chunks_written: int = 0
    embeddings_written: int = 0
    documents_deactivated: int = 0
    database_failures: int = 0
    failed_paths: list[str] = field(default_factory=list)
    seen_source_paths: set[str] = field(default_factory=set, repr=False)


@dataclass(frozen=True)
class IngestionPreflight:
    corpus_path: Path
    supported_files: int
    nonempty_english_files: int
    prepared: list[PreparedDocument] = field(repr=False)
    summary: IngestionSummary = field(repr=False)


def run_ingestion_preflight(config: IngestionConfig) -> IngestionPreflight:
    if config.backend != RagBackend.PGVECTOR:
        raise ValueError("Ingestion requires RAG_BACKEND=pgvector.")
    validate_embedding_contract(
        provider=config.embedding_provider,
        model_name=config.model_name,
        dimensions=config.embedding_dimensions,
        openai_api_key=config.openai_api_key,
    )
    corpus_path = config.repo_path.resolve()
    if not corpus_path.exists():
        raise FileNotFoundError(
            f"RAG corpus source path does not exist: {corpus_path}. "
            "Run `uv run python -m backend.ingestion.fetch_corpus` or set "
            "RAG_CORPUS_SOURCE_PATH to an existing Full Stack Open checkout."
        )
    if not corpus_path.is_dir():
        raise ValueError(f"RAG corpus source path is not a directory: {corpus_path}")

    prepared, summary = prepare_corpus(config)
    if summary.discovered_files == 0:
        raise ValueError(
            f"RAG corpus source path contains no supported files: {corpus_path}. "
            "Expected .md, .txt, .py, or .ipynb course sources."
        )
    if not prepared:
        raise ValueError(
            f"RAG corpus source path contains no usable English course files: {corpus_path}. "
            "Expected non-empty English sources that produce at least one chunk."
        )
    return IngestionPreflight(
        corpus_path=corpus_path,
        supported_files=summary.discovered_files,
        nonempty_english_files=summary.prepared_documents,
        prepared=prepared,
        summary=summary,
    )


def prepare_corpus(config: IngestionConfig) -> tuple[list[PreparedDocument], IngestionSummary]:
    repo_root = config.repo_path.resolve()
    if config.chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")
    if config.chunk_overlap < 0 or config.chunk_overlap >= config.chunk_size:
        raise ValueError("chunk_overlap must be between 0 and chunk_size - 1")
    if config.min_chunk_chars < 0:
        raise ValueError("min_chunk_chars must be at least 0")
    if config.max_oversized_code_chars < config.chunk_size:
        raise ValueError("max_oversized_code_chars must be at least chunk_size")
    if config.embedding_batch_size < 1:
        raise ValueError("embedding_batch_size must be at least 1")

    files = sorted(find_course_files(repo_root))
    summary = IngestionSummary(discovered_files=len(files))
    prepared = []

    for path in files:
        relative_path = path.relative_to(repo_root).as_posix()
        try:
            document = make_document(path, repo_root)
            document["id"] = relative_path
            document["metadata"]["source_path"] = relative_path
            if not is_english_source(document):
                summary.skipped_non_english += 1
                continue
            summary.seen_source_paths.add(relative_path)
            if not document["content"]:
                summary.skipped_empty += 1
                continue

            chunks = prepare_chunks(
                SourceDocument(
                    content=document["content"],
                    source_type=config.source_type,
                    source_path=relative_path,
                    document_id=relative_path,
                    metadata=dict(document["metadata"]),
                ),
                chunk_size=config.chunk_size,
                overlap=config.chunk_overlap,
                min_chunk_chars=config.min_chunk_chars,
                max_oversized_code_chars=config.max_oversized_code_chars,
            )
            if not chunks:
                summary.skipped_empty += 1
                continue

            prepared.append(
                PreparedDocument(
                    source_path=relative_path,
                    title=document["metadata"].get("file_name"),
                    content_hash=content_hash(document["content"]),
                    metadata=dict(document["metadata"]),
                    chunks=chunks,
                )
            )
            summary.prepared_chunks += len(chunks)
        except Exception:
            summary.preprocessing_failures += 1
            summary.failed_paths.append(relative_path)
            logger.exception("Failed to preprocess source file: %s", relative_path)
            if config.fail_fast:
                raise

    summary.prepared_documents = len(prepared)
    return prepared, summary


async def ingest_corpus(
    config: IngestionConfig,
    *,
    preflight: IngestionPreflight | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    session_factory: SessionFactoryCallable = SessionFactory,
    service_factory: RagServiceFactory = RagService,
) -> IngestionSummary:
    preflight = preflight or run_ingestion_preflight(config)
    prepared = preflight.prepared
    summary = preflight.summary
    _log_preprocessing_summary(summary)

    if config.dry_run:
        logger.info(
            "Dry run complete: would write documents=%d chunks=%d embeddings=%d",
            summary.prepared_documents,
            summary.prepared_chunks,
            summary.prepared_chunks,
        )
        return summary

    if not prepared:
        logger.warning("No documents were prepared; nothing will be written.")
        return summary

    provider = embedding_provider or get_embedding_provider(
        config.embedding_provider,
        config.model_name,
        config.embedding_dimensions,
        config.openai_api_key,
    )

    all_chunks = [chunk for document in prepared for chunk in document.chunks]
    logger.info(
        "Generating embeddings: provider=%s model=%s dimensions=%d chunks=%d batch_size=%d",
        provider.provider_name,
        config.model_name,
        config.embedding_dimensions,
        len(all_chunks),
        config.embedding_batch_size,
    )
    vectors = []
    chunk_texts = [chunk.content for chunk in all_chunks]
    for offset in range(0, len(chunk_texts), config.embedding_batch_size):
        vectors.extend(
            provider.embed_texts(chunk_texts[offset : offset + config.embedding_batch_size])
        )
    if len(vectors) != len(all_chunks):
        raise ValueError("Embedding provider returned a different number of vectors than chunks.")

    vector_offset = 0
    async with session_factory() as session:
        service = service_factory(session=session)
        for document in prepared:
            document_vectors = vectors[vector_offset : vector_offset + len(document.chunks)]
            vector_offset += len(document.chunks)
            try:
                chunks = [
                    ChunkRecord(
                        id=chunk.chunk_id,
                        chunk_index=chunk.chunk_index,
                        content=chunk.content,
                        content_hash=chunk.content_hash,
                        char_start=chunk.char_start,
                        char_end=chunk.char_end,
                        heading_path=chunk.heading_path,
                        section_heading=chunk.section_heading,
                        chunk_type=chunk.chunk_type,
                        chunker_version=chunk.chunker_version,
                        metadata=chunk.persistence_metadata(),
                    )
                    for chunk in document.chunks
                ]
                embeddings = [
                    EmbeddingRecord(
                        chunk_id=chunk.id,
                        embedding=vector,
                        embedding_provider=config.embedding_provider.value,
                        embedding_model=config.model_name,
                        embedding_dimensions=config.embedding_dimensions,
                    )
                    for chunk, vector in zip(chunks, document_vectors, strict=True)
                ]
                await service.replace_document_index(
                    source_type=config.source_type,
                    source_path=document.source_path,
                    content_hash=document.content_hash,
                    title=document.title,
                    course_name=config.course_name,
                    metadata=document.metadata,
                    chunks=chunks,
                    embeddings=embeddings,
                )
                summary.documents_written += 1
                summary.chunks_written += len(chunks)
                summary.embeddings_written += len(embeddings)
                logger.info(
                    "Indexed document: source=%s chunks=%d embeddings=%d",
                    document.source_path,
                    len(chunks),
                    len(embeddings),
                )
            except Exception:
                summary.database_failures += 1
                summary.failed_paths.append(document.source_path)
                logger.exception("Failed to index document: %s", document.source_path)
                if config.fail_fast:
                    raise

        if _can_reconcile(config, summary):
            try:
                summary.documents_deactivated = await service.reconcile_documents(
                    source_type=config.source_type,
                    course_name=config.course_name,
                    seen_source_paths=sorted(summary.seen_source_paths),
                )
            except Exception:
                summary.database_failures += 1
                logger.exception("Failed to reconcile missing source documents.")
                if config.fail_fast:
                    raise
        elif config.reconcile_deletions:
            logger.warning(
                "Deletion reconciliation skipped: dry_run=%s prepared=%d "
                "preprocessing_failures=%d database_failures=%d seen=%d",
                config.dry_run,
                summary.prepared_documents,
                summary.preprocessing_failures,
                summary.database_failures,
                len(summary.seen_source_paths),
            )

    _log_write_summary(summary)
    return summary


def _can_reconcile(config: IngestionConfig, summary: IngestionSummary) -> bool:
    return (
        config.reconcile_deletions
        and not config.dry_run
        and summary.prepared_documents > 0
        and bool(summary.seen_source_paths)
        and summary.preprocessing_failures == 0
        and summary.database_failures == 0
    )


def _log_preprocessing_summary(summary: IngestionSummary) -> None:
    logger.info(
        (
            "Preprocessing complete: discovered=%d documents=%d chunks=%d "
            "skipped_non_english=%d skipped_empty=%d failures=%d"
        ),
        summary.discovered_files,
        summary.prepared_documents,
        summary.prepared_chunks,
        summary.skipped_non_english,
        summary.skipped_empty,
        summary.preprocessing_failures,
    )


def _log_write_summary(summary: IngestionSummary) -> None:
    logger.info(
        (
            "Postgres ingestion complete: documents=%d chunks=%d embeddings=%d "
            "deactivated=%d failures=%d"
        ),
        summary.documents_written,
        summary.chunks_written,
        summary.embeddings_written,
        summary.documents_deactivated,
        summary.database_failures,
    )


def build_parser(settings: RagSettings | None = None) -> argparse.ArgumentParser:
    settings = settings or RagSettings()
    parser = argparse.ArgumentParser(
        description="Rebuild PostgreSQL/pgvector RAG records from a course repository."
    )
    parser.add_argument(
        "--repo-path",
        type=Path,
        default=settings.corpus_source_path,
        help="Corpus source directory; defaults to RAG_CORPUS_SOURCE_PATH.",
    )
    parser.add_argument("--source-type", default="course_repo")
    parser.add_argument("--course-name", default="Full Stack Open")
    parser.add_argument(
        "--embedding-provider",
        choices=[provider.value for provider in RagEmbeddingProvider],
        default=settings.embedding_provider.value,
    )
    parser.add_argument("--model-name", default=settings.model_name)
    parser.add_argument(
        "--embedding-dimensions",
        type=int,
        default=settings.embedding_dimensions,
    )
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--chunk-overlap", type=int, default=DEFAULT_CHUNK_OVERLAP)
    parser.add_argument("--min-chunk-chars", type=int, default=DEFAULT_MIN_CHUNK_CHARS)
    parser.add_argument(
        "--max-oversized-code-chars",
        type=int,
        default=DEFAULT_MAX_OVERSIZED_CODE_CHARS,
    )
    parser.add_argument(
        "--embedding-batch-size",
        type=int,
        default=DEFAULT_EMBEDDING_BATCH_SIZE,
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Validate corpus, embedding configuration, and DATABASE_URL without ingestion.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preprocess and report counts without loading the model or connecting to Postgres.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on the first preprocessing or database failure.",
    )
    parser.add_argument(
        "--reconcile-deletions",
        action="store_true",
        help="Deactivate previously indexed source documents missing from a successful scan.",
    )
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = RagSettings()
    args = build_parser(settings).parse_args()
    config = build_ingestion_config(args, settings)
    validate_cli_database_url(
        app_settings.database_url,
        dry_run=args.dry_run,
        preflight_only=args.preflight_only,
    )
    preflight = run_ingestion_preflight(config)
    logger.info(
        "Ingestion preflight passed: corpus=%s supported_files=%d english_files=%d "
        "provider=%s model=%s dimensions=%d",
        preflight.corpus_path,
        preflight.supported_files,
        preflight.nonempty_english_files,
        config.embedding_provider.value,
        config.model_name,
        config.embedding_dimensions,
    )
    if args.preflight_only:
        return
    asyncio.run(ingest_corpus(config, preflight=preflight))


def validate_cli_database_url(
    database_url: str,
    *,
    dry_run: bool,
    preflight_only: bool = False,
) -> None:
    if (not dry_run or preflight_only) and not database_url.strip():
        raise ValueError(
            "DATABASE_URL is required for pgvector ingestion. Set it to the target Render "
            "PostgreSQL URL before running ingestion."
        )


def build_ingestion_config(
    args: argparse.Namespace,
    settings: RagSettings,
) -> IngestionConfig:
    embedding_settings = RagSettings(
        _env_file=None,
        backend=RagBackend.PGVECTOR,
        embedding_provider=args.embedding_provider,
        model_name=args.model_name,
        embedding_dimensions=args.embedding_dimensions,
        OPENAI_API_KEY=settings.openai_api_key,
    )
    return IngestionConfig(
        repo_path=args.repo_path,
        backend=embedding_settings.backend,
        source_type=args.source_type,
        course_name=args.course_name,
        embedding_provider=embedding_settings.embedding_provider,
        model_name=embedding_settings.model_name,
        embedding_dimensions=embedding_settings.embedding_dimensions,
        openai_api_key=embedding_settings.openai_api_key,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        min_chunk_chars=args.min_chunk_chars,
        max_oversized_code_chars=args.max_oversized_code_chars,
        embedding_batch_size=args.embedding_batch_size,
        dry_run=args.dry_run,
        fail_fast=args.fail_fast,
        reconcile_deletions=args.reconcile_deletions,
    )


if __name__ == "__main__":
    main()
