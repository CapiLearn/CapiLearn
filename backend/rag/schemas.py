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
