from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.rag.models import EMBEDDING_DIMENSIONS, RagChunk, RagDocument, RagEmbedding
from backend.rag.repository import (
    ChunkRecord,
    EmbeddingRecord,
    RagRepository,
    SimilarChunk,
)


class RagService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        repository: RagRepository | None = None,
    ) -> None:
        self._session = session
        self._repository = repository or RagRepository()

    async def upsert_document(
        self,
        *,
        source_type: str,
        source_path: str,
        content_hash: str,
        title: str | None = None,
        course_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RagDocument:
        document = await self._repository.upsert_document(
            self._session,
            source_type=source_type,
            source_path=source_path,
            content_hash=content_hash,
            title=title,
            course_name=course_name,
            metadata=metadata,
        )
        await self._session.commit()
        return document

    async def replace_chunks(
        self,
        *,
        document_id: UUID,
        chunks: Sequence[ChunkRecord],
    ) -> list[RagChunk]:
        await self._repository.delete_chunks(self._session, document_id=document_id)
        rows = await self._repository.insert_chunks(
            self._session,
            document_id=document_id,
            chunks=chunks,
        )
        await self._session.commit()
        return rows

    async def insert_chunks(
        self,
        *,
        document_id: UUID,
        chunks: Sequence[ChunkRecord],
    ) -> list[RagChunk]:
        rows = await self._repository.insert_chunks(
            self._session,
            document_id=document_id,
            chunks=chunks,
        )
        await self._session.commit()
        return rows

    async def insert_embeddings(
        self,
        *,
        embeddings: Sequence[EmbeddingRecord],
    ) -> list[RagEmbedding]:
        for record in embeddings:
            _validate_embedding(record.embedding)
        rows = await self._repository.insert_embeddings(
            self._session,
            embeddings=embeddings,
        )
        await self._session.commit()
        return rows

    async def reconcile_documents(
        self,
        *,
        source_type: str,
        course_name: str,
        seen_source_paths: Sequence[str],
    ) -> int:
        if not seen_source_paths:
            raise ValueError("seen_source_paths must not be empty")
        try:
            count = await self._repository.deactivate_missing_documents(
                self._session,
                source_type=source_type,
                course_name=course_name,
                seen_source_paths=seen_source_paths,
            )
            await self._session.commit()
            return count
        except Exception:
            await self._session.rollback()
            raise

    async def replace_document_index(
        self,
        *,
        source_type: str,
        source_path: str,
        content_hash: str,
        chunks: Sequence[ChunkRecord],
        embeddings: Sequence[EmbeddingRecord],
        title: str | None = None,
        course_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RagDocument:
        _validate_chunk_embeddings(chunks=chunks, embeddings=embeddings)
        try:
            document = await self._repository.upsert_document(
                self._session,
                source_type=source_type,
                source_path=source_path,
                content_hash=content_hash,
                title=title,
                course_name=course_name,
                metadata=metadata,
            )
            await self._repository.delete_chunks(
                self._session,
                document_id=document.id,
            )
            await self._repository.insert_chunks(
                self._session,
                document_id=document.id,
                chunks=chunks,
            )
            await self._repository.insert_embeddings(
                self._session,
                embeddings=embeddings,
            )
            await self._session.commit()
            return document
        except Exception:
            await self._session.rollback()
            raise

    async def retrieve(
        self,
        *,
        query_embedding: Sequence[float],
        embedding_provider: str,
        embedding_model: str,
        embedding_dimensions: int,
        top_k: int = 5,
    ) -> list[SimilarChunk]:
        _validate_embedding(query_embedding)
        if top_k < 1:
            raise ValueError("top_k must be at least 1")

        results = await self._repository.find_similar_chunks(
            self._session,
            query_embedding=query_embedding,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            embedding_dimensions=embedding_dimensions,
            top_k=top_k,
        )
        return results


def _validate_embedding(embedding: Sequence[float]) -> None:
    if len(embedding) != EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"Embeddings must contain exactly {EMBEDDING_DIMENSIONS} dimensions; "
            f"received {len(embedding)}."
        )


def _validate_chunk_embeddings(
    *,
    chunks: Sequence[ChunkRecord],
    embeddings: Sequence[EmbeddingRecord],
) -> None:
    chunk_ids = {chunk.id for chunk in chunks}
    if None in chunk_ids:
        raise ValueError("Chunk IDs are required when replacing a document index.")
    if len(chunk_ids) != len(chunks):
        raise ValueError("Chunk IDs must be unique when replacing a document index.")
    chunk_indexes = {chunk.chunk_index for chunk in chunks}
    if len(chunk_indexes) != len(chunks):
        raise ValueError("Chunk indexes must be unique within a document.")
    if len(embeddings) != len(chunks):
        raise ValueError("Each chunk must have exactly one embedding.")

    embedding_chunk_ids = {record.chunk_id for record in embeddings}
    if embedding_chunk_ids != chunk_ids:
        raise ValueError("Embedding chunk IDs must match the supplied chunk IDs.")
    for record in embeddings:
        _validate_embedding(record.embedding)
