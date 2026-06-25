"""Shared schemas and provider protocols for LLM orchestration."""

from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from backend.rag.schemas import RetrievalResult, RetrievedChunk


class LLMBaseModel(BaseModel):
    """Base model using camelCase aliases for API and log payloads."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="ignore",
    )


class ChatRole(StrEnum):
    """Roles supported by chat completion providers."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(LLMBaseModel):
    """One provider-compatible chat message."""

    role: ChatRole
    content: str


class GuardrailResult(LLMBaseModel):
    """Normalized result returned by any guardrail provider."""

    blocked: bool = False
    reason: str | None = None
    rail: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMRequest(LLMBaseModel):
    """Request envelope for generating a response to one user message."""

    user_id: UUID
    conversation_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID
    content: str
    history: list[ChatMessage] = Field(default_factory=list)


class ProviderResponse(LLMBaseModel):
    """Normalized response and usage metadata from an LLM provider."""

    content: str
    model: str | None = None
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: int | None = None


class LLMCostComponent(LLMBaseModel):
    """Cost and usage record for one provider-backed LLM component call."""

    user_id: UUID
    conversation_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID
    component_order: int
    component_type: str
    attempt_index: int = 1
    provider: str | None = None
    configured_model: str | None = None
    response_model: str | None = None
    finish_reason: str | None = None
    status: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost_usd: Decimal | None = None
    latency_ms: int | None = None
    error_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMResult(LLMBaseModel):
    """Final response payload returned by the LLM service."""

    content: str
    retrieval_result: RetrievalResult = Field(default_factory=RetrievalResult)
    retrieved_context: list[RetrievedChunk] = Field(default_factory=list)
    input_guardrail_result: GuardrailResult = Field(default_factory=GuardrailResult)
    output_guardrail_result: GuardrailResult = Field(default_factory=GuardrailResult)
    provider_response: ProviderResponse | None = None
    cost_components: list[LLMCostComponent] = Field(default_factory=list)


class LLMProvider(Protocol):
    """Protocol for chat completion providers consumed by LLMService."""

    async def complete(self, messages: list[ChatMessage]) -> ProviderResponse: ...


class GuardrailsProvider(Protocol):
    """Protocol for input and output guardrail providers."""

    async def check_input(self, content: str) -> GuardrailResult: ...

    async def check_output(
        self,
        content: str,
        *,
        user_input: str,
    ) -> GuardrailResult: ...
