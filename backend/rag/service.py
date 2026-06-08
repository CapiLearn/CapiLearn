import asyncio
from collections.abc import Callable, Sequence
from threading import Lock
from typing import Any, ClassVar
from uuid import UUID

from sentence_transformers import SentenceTransformer
from sqlalchemy.ext.asyncio import AsyncSession

from backend.rag.models import EMBEDDING_DIMENSIONS, RagChunk, RagDocument, RagEmbedding
from backend.rag.repository import (
    ChunkRecord,
    EmbeddingRecord,
    RagRepository,
    SimilarChunk,
)


class RagService:
    _model_cache: ClassVar[dict[tuple[int, str], Any]] = {}
    _model_loader_refs: ClassVar[dict[int, Callable[[str], Any]]] = {}
    _model_cache_lock: ClassVar[Lock] = Lock()

    def __init__(
        self,
        *,
        session: AsyncSession,
        repository: RagRepository | None = None,
        model_loader: Callable[[str], Any] = SentenceTransformer,
    ) -> None:
        self._session = session
        self._repository = repository or RagRepository()
        self._model_loader = model_loader

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
        query_text: str,
        query_embedding: Sequence[float],
        embedding_model: str,
        top_k: int = 5,
        write_log: bool = False,
        conversation_id: UUID | None = None,
        message_id: UUID | None = None,
        rag_index_version: str | None = None,
    ) -> list[SimilarChunk]:
        _validate_embedding(query_embedding)
        if top_k < 1:
            raise ValueError("top_k must be at least 1")

        results = await self._repository.find_similar_chunks(
            self._session,
            query_embedding=query_embedding,
            embedding_model=embedding_model,
            top_k=top_k,
        )
        if write_log:
            await self._repository.write_retrieval_log(
                self._session,
                query_text=query_text,
                results=results,
                conversation_id=conversation_id,
                message_id=message_id,
                rag_index_version=rag_index_version,
            )
            await self._session.commit()
        return results

    async def retrieve_by_text(
        self,
        *,
        query_text: str,
        embedding_model: str,
        top_k: int = 5,
        write_log: bool = False,
        conversation_id: UUID | None = None,
        message_id: UUID | None = None,
        rag_index_version: str | None = None,
    ) -> list[SimilarChunk]:
        query_embedding = await asyncio.to_thread(
            self._embed_query,
            query_text,
            embedding_model,
        )
        return await self.retrieve(
            query_text=query_text,
            query_embedding=query_embedding,
            embedding_model=embedding_model,
            top_k=top_k,
            write_log=write_log,
            conversation_id=conversation_id,
            message_id=message_id,
            rag_index_version=rag_index_version,
        )

    def _embed_query(self, query_text: str, embedding_model: str) -> list[float]:
        model = self._get_model(embedding_model)
        embedding = model.encode(query_text)
        return embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)

    def _get_model(self, embedding_model: str) -> Any:
        loader_id = id(self._model_loader)
        cache_key = (loader_id, embedding_model)
        if cache_key not in self._model_cache:
            with self._model_cache_lock:
                if cache_key not in self._model_cache:
                    self._model_loader_refs[loader_id] = self._model_loader
                    self._model_cache[cache_key] = self._model_loader(embedding_model)
        return self._model_cache[cache_key]


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
    if len(embeddings) != len(chunks):
        raise ValueError("Each chunk must have exactly one embedding.")

    embedding_chunk_ids = {record.chunk_id for record in embeddings}
    if embedding_chunk_ids != chunk_ids:
        raise ValueError("Embedding chunk IDs must match the supplied chunk IDs.")
    for record in embeddings:
        _validate_embedding(record.embedding)
