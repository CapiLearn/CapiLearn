from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
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
                    "metadata": metadata or {},
                    "updated_at": utc_now(),
                },
            )
            .returning(RagDocument)
            .execution_options(populate_existing=True)
        )
        result = await session.execute(statement)
        return result.scalar_one()

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
                extra_metadata=chunk.metadata or {},
            )
            if chunk.id is not None
            else RagChunk(
                document_id=document_id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                token_count=chunk.token_count,
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
                RagDocument.source_type,
                RagDocument.source_path,
                RagDocument.title,
                RagDocument.course_name,
                distance,
            )
            .join(RagEmbedding, RagEmbedding.chunk_id == RagChunk.id)
            .join(RagDocument, RagDocument.id == RagChunk.document_id)
            .where(RagEmbedding.embedding_model == embedding_model)
            .order_by(distance)
            .limit(top_k)
        )
        rows = (await session.execute(statement)).all()
        return [
            SimilarChunk(
                chunk_id=row[0],
                document_id=row[1],
                content=row[2],
                metadata=row[3] or {},
                source_type=row[4],
                source_path=row[5],
                title=row[6],
                course_name=row[7],
                distance=float(row[8]),
                similarity=1.0 - float(row[8]),
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
