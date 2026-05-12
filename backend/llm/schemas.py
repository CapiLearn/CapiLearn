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
    content: str
    source_id: str
    title: str
    page: int | None = None
    url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GuardrailResult(LLMBaseModel):
    blocked: bool = False
    reason: str | None = None
    rail: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMRequest(LLMBaseModel):
    user_id: UUID
    conversation_id: UUID
    message_id: UUID
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
    ) -> list[RetrievedChunk]: ...


class LLMProvider(Protocol):
    async def complete(self, messages: list[ChatMessage]) -> ProviderResponse: ...


class GuardrailsProvider(Protocol):
    has_output_guardrail: bool

    async def check_input(self, content: str) -> GuardrailResult: ...

    async def check_output(
        self,
        content: str,
        *,
        user_input: str,
    ) -> GuardrailResult: ...
