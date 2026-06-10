from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class RagBaseModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="ignore",
    )


class RetrievedChunk(RagBaseModel):
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    distance: float | None = None
    similarity: float | None = None


class RetrievalResult(RagBaseModel):
    chunks: list[RetrievedChunk] = Field(default_factory=list)


class RagRetrievedChunkLogRecord(RagBaseModel):
    chunk_id: UUID | str
    document_id: UUID | str | None = None
    rank: int | None = None
    score: float | None = None
    distance: float | None = None
    similarity: float | None = None
    source_type: str | None = None
    source_path: str | None = None
    title: str | None = None


class RagRetrievalLogRecord(RagBaseModel):
    query_text: str
    conversation_id: UUID | str | None = None
    user_message_id: UUID | str | None = None
    chunks: list[RagRetrievedChunkLogRecord] = Field(default_factory=list)


class RetrievalProvider(Protocol):
    async def retrieve(
        self,
        query: str,
        *,
        user_id: UUID,
        conversation_id: UUID,
        user_message_id: UUID,
    ) -> RetrievalResult: ...


def build_rag_retrieval_log_record(
    *,
    query_text: str,
    result: RetrievalResult,
    conversation_id: UUID | str | None = None,
    user_message_id: UUID | str | None = None,
) -> RagRetrievalLogRecord:
    chunks = []
    for rank, chunk in enumerate(result.chunks, start=1):
        metadata = chunk.metadata or {}
        chunk_id = metadata.get("chunk_id")
        if chunk_id is None:
            continue
        chunks.append(
            RagRetrievedChunkLogRecord(
                chunk_id=chunk_id,
                document_id=metadata.get("document_id"),
                rank=rank,
                score=metadata.get("score"),
                distance=chunk.distance,
                similarity=chunk.similarity,
                source_type=metadata.get("source_type"),
                source_path=metadata.get("source_path"),
                title=metadata.get("title"),
            )
        )
    return RagRetrievalLogRecord(
        query_text=query_text,
        conversation_id=conversation_id,
        user_message_id=user_message_id,
        chunks=chunks,
    )


def retrieval_chunk_log_metadata(chunk: RetrievedChunk) -> dict[str, Any]:
    metadata = chunk.metadata or {}
    allowed_keys = {
        "source_id",
        "sourceId",
        "chunk_id",
        "chunkId",
        "document_id",
        "documentId",
        "title",
        "source_path",
        "sourcePath",
        "heading_path",
        "headingPath",
        "section_heading",
        "sectionHeading",
        "chunk_type",
        "chunkType",
        "content_hash",
        "contentHash",
        "char_start",
        "charStart",
        "char_end",
        "charEnd",
        "page",
        "score",
        "distance",
        "similarity",
    }
    fields = {key: metadata[key] for key in allowed_keys if key in metadata}
    if chunk.distance is not None:
        fields["distance"] = chunk.distance
    if chunk.similarity is not None:
        fields["similarity"] = chunk.similarity
    return fields
