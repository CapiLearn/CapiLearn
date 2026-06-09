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


class RetrievalProvider(Protocol):
    async def retrieve(
        self,
        query: str,
        *,
        user_id: UUID,
        conversation_id: UUID,
        user_message_id: UUID,
    ) -> RetrievalResult: ...


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
