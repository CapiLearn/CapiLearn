from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class LLMBaseModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ChatRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(LLMBaseModel):
    role: ChatRole
    content: str


class RetrievedChunk(LLMBaseModel):
    chunk_id: str | None = None
    content: str
    source_id: str
    source_title: str | None = None
    source_type: str | None = None
    section_title: str | None = None
    title: str | None = None
    relevance_score: float | None = None
    rank: int | None = None
    page: int | None = None
    url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalResult(LLMBaseModel):
    user_message_id: UUID | None = None
    student_question: str | None = None
    normalized_query: str | None = None
    retrieval_status: str = "success"
    retrieval_confidence: str | None = None
    top_k: int | None = None
    chunks: list[RetrievedChunk] = Field(default_factory=list)
    retrieval_notes: dict[str, Any] = Field(default_factory=dict)


class GuardrailResult(LLMBaseModel):
    blocked: bool = False
    reason: str | None = None
    rail: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMRequest(LLMBaseModel):
    user_id: UUID
    conversation_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID | None = None
    content: str
    history: list[ChatMessage] = Field(default_factory=list)


class ProviderResponse(LLMBaseModel):
    content: str
    model: str | None = None
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    raw_response: dict[str, Any] | None = None


class LLMResult(LLMBaseModel):
    content: str
    retrieval_result: RetrievalResult = Field(default_factory=RetrievalResult)
    retrieved_context: list[RetrievedChunk] = Field(default_factory=list)
    input_guardrail_result: GuardrailResult = Field(default_factory=GuardrailResult)
    output_guardrail_result: GuardrailResult = Field(default_factory=GuardrailResult)
    provider_response: ProviderResponse | None = None


class RetrievalProvider(Protocol):
    async def retrieve(
        self,
        query: str,
        *,
        user_id: UUID,
        conversation_id: UUID,
        user_message_id: UUID,
    ) -> RetrievalResult: ...


class LLMProvider(Protocol):
    async def complete(self, messages: list[ChatMessage]) -> ProviderResponse: ...


class GuardrailsProvider(Protocol):
    async def check_input(self, content: str) -> GuardrailResult: ...

    async def check_output(
        self,
        content: str,
        *,
        user_input: str,
    ) -> GuardrailResult: ...
