from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.rag.models import (
    RagChunk,
    RagDocument,
    RagEmbedding,
    RagRetrievalLog,
    utc_now,
)


@dataclass(frozen=True)
class ChunkRecord:
    chunk_index: int
    content: str
    token_count: int | None = None
    content_hash: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    heading_path: tuple[str, ...] = ()
    section_heading: str | None = None
    chunk_type: str | None = None
    chunker_version: str | None = None
    metadata: dict[str, Any] | None = None
    id: UUID | None = None


@dataclass(frozen=True)
class EmbeddingRecord:
    chunk_id: UUID
    embedding: Sequence[float]
    embedding_model: str


@dataclass(frozen=True)
class SimilarChunk:
    chunk_id: UUID
    document_id: UUID
    content: str
    metadata: dict[str, Any]
    source_type: str
    source_path: str
    title: str | None
    course_name: str | None
    distance: float
    similarity: float


class RagRepository:
    async def upsert_document(
        self,
        session: AsyncSession,
        *,
        source_type: str,
        source_path: str,
        content_hash: str,
        title: str | None = None,
        course_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RagDocument:
        statement = (
            insert(RagDocument)
            .values(
                source_type=source_type,
                source_path=source_path,
                title=title,
                course_name=course_name,
                content_hash=content_hash,
                is_active=True,
                deleted_at=None,
                extra_metadata=metadata or {},
            )
            .on_conflict_do_update(
                index_elements=[
                    RagDocument.source_type,
                    RagDocument.source_path,
                ],
                set_={
                    "title": title,
                    "course_name": course_name,
                    "content_hash": content_hash,
                    "is_active": True,
                    "deleted_at": None,
                    "metadata": metadata or {},
                    "updated_at": utc_now(),
                },
            )
            .returning(RagDocument)
            .execution_options(populate_existing=True)
        )
        result = await session.execute(statement)
        return result.scalar_one()

    async def deactivate_missing_documents(
        self,
        session: AsyncSession,
        *,
        source_type: str,
        course_name: str,
        seen_source_paths: Sequence[str],
    ) -> int:
        if not seen_source_paths:
            raise ValueError("seen_source_paths must not be empty")
        statement = (
            update(RagDocument)
            .where(
                RagDocument.source_type == source_type,
                RagDocument.course_name == course_name,
                RagDocument.is_active.is_(True),
                RagDocument.source_path.not_in(list(seen_source_paths)),
            )
            .values(is_active=False, deleted_at=utc_now(), updated_at=utc_now())
        )
        result = await session.execute(statement)
        return result.rowcount or 0

    async def deactivate_documents_by_source_paths(
        self,
        session: AsyncSession,
        *,
        source_type: str,
        source_paths: Sequence[str],
    ) -> int:
        if not source_paths:
            raise ValueError("source_paths must not be empty")
        statement = (
            update(RagDocument)
            .where(
                RagDocument.source_type == source_type,
                RagDocument.is_active.is_(True),
                RagDocument.source_path.in_(list(source_paths)),
            )
            .values(is_active=False, deleted_at=utc_now(), updated_at=utc_now())
        )
        result = await session.execute(statement)
        return result.rowcount or 0

    async def insert_chunks(
        self,
        session: AsyncSession,
        *,
        document_id: UUID,
        chunks: Sequence[ChunkRecord],
    ) -> list[RagChunk]:
        rows = [
            RagChunk(
                id=chunk.id,
                document_id=document_id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                token_count=chunk.token_count,
                content_hash=chunk.content_hash,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                heading_path=list(chunk.heading_path),
                section_heading=chunk.section_heading,
                chunk_type=chunk.chunk_type,
                chunker_version=chunk.chunker_version,
                extra_metadata=chunk.metadata or {},
            )
            if chunk.id is not None
            else RagChunk(
                document_id=document_id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                token_count=chunk.token_count,
                content_hash=chunk.content_hash,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                heading_path=list(chunk.heading_path),
                section_heading=chunk.section_heading,
                chunk_type=chunk.chunk_type,
                chunker_version=chunk.chunker_version,
                extra_metadata=chunk.metadata or {},
            )
            for chunk in chunks
        ]
        session.add_all(rows)
        await session.flush()
        return rows

    async def delete_chunks(
        self,
        session: AsyncSession,
        *,
        document_id: UUID,
    ) -> None:
        await session.execute(delete(RagChunk).where(RagChunk.document_id == document_id))

    async def insert_embeddings(
        self,
        session: AsyncSession,
        *,
        embeddings: Sequence[EmbeddingRecord],
    ) -> list[RagEmbedding]:
        rows = [
            RagEmbedding(
                chunk_id=record.chunk_id,
                embedding=list(record.embedding),
                embedding_model=record.embedding_model,
            )
            for record in embeddings
        ]
        session.add_all(rows)
        await session.flush()
        return rows

    async def find_similar_chunks(
        self,
        session: AsyncSession,
        *,
        query_embedding: Sequence[float],
        embedding_model: str,
        top_k: int,
    ) -> list[SimilarChunk]:
        distance = RagEmbedding.embedding.cosine_distance(list(query_embedding)).label("distance")
        statement = (
            select(
                RagChunk.id,
                RagChunk.document_id,
                RagChunk.content,
                RagChunk.extra_metadata,
                RagChunk.content_hash,
                RagChunk.char_start,
                RagChunk.char_end,
                RagChunk.heading_path,
                RagChunk.section_heading,
                RagChunk.chunk_type,
                RagChunk.chunker_version,
                RagDocument.source_type,
                RagDocument.source_path,
                RagDocument.title,
                RagDocument.course_name,
                distance,
            )
            .join(RagEmbedding, RagEmbedding.chunk_id == RagChunk.id)
            .join(RagDocument, RagDocument.id == RagChunk.document_id)
            .where(
                RagEmbedding.embedding_model == embedding_model,
                RagDocument.is_active.is_(True),
            )
            .order_by(distance)
            .limit(top_k)
        )
        rows = (await session.execute(statement)).all()
        return [
            SimilarChunk(
                chunk_id=row[0],
                document_id=row[1],
                content=row[2],
                metadata={
                    **(row[3] or {}),
                    "content_hash": row[4],
                    "char_start": row[5],
                    "char_end": row[6],
                    "heading_path": row[7] or [],
                    "section_heading": row[8],
                    "chunk_type": row[9],
                    "chunker_version": row[10],
                },
                source_type=row[11],
                source_path=row[12],
                title=row[13],
                course_name=row[14],
                distance=float(row[15]),
                similarity=1.0 - float(row[15]),
            )
            for row in rows
        ]

    async def write_retrieval_log(
        self,
        session: AsyncSession,
        *,
        query_text: str,
        retrieved_chunk_ids: Sequence[str],
        scores: Sequence[dict[str, Any]],
        conversation_id: UUID | None = None,
        message_id: UUID | None = None,
        rag_index_version: str | None = None,
    ) -> RagRetrievalLog:
        log = RagRetrievalLog(
            conversation_id=conversation_id,
            message_id=message_id,
            query_text=query_text,
            retrieved_chunk_ids=list(retrieved_chunk_ids),
            scores=list(scores),
            rag_index_version=rag_index_version,
        )
        session.add(log)
        await session.flush()
        return log
