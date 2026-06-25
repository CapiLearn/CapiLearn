"""Pydantic schemas and enums for the chat API contract."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from backend.core.citations import CitationRecord

MAX_MESSAGE_CONTENT_LENGTH = 8000


class ChatBaseModel(BaseModel):
    """Base schema with the chat API's camelCase JSON contract."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class ConversationStatus(StrEnum):
    """Lifecycle states for a conversation."""

    ACTIVE = "active"
    DELETED = "deleted"


class MessageRole(StrEnum):
    """Roles supported by stored chat messages."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    CONTEXT = "context"


class MessageStatus(StrEnum):
    """Lifecycle states for an assistant or user message."""

    PENDING = "pending"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


class StoredRagHistoryContext(ChatBaseModel):
    """Compact RAG context persisted for later conversation-history prompts."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
    )

    heading: str | None = None
    content: str


class SendMessageRequest(ChatBaseModel):
    """Request body for starting or continuing a conversation."""

    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CONTENT_LENGTH)


class ConversationResponse(ChatBaseModel):
    """Conversation summary returned by chat endpoints."""

    id: UUID
    title: str | None
    updated_at: datetime


class ConversationListResponse(ChatBaseModel):
    """Response body for listing conversations."""

    conversations: list[ConversationResponse]


class MessageResponse(ChatBaseModel):
    """Message representation returned by chat endpoints."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    conversation_id: UUID
    role: MessageRole
    content: str
    status: MessageStatus
    created_at: datetime
    citations: list[CitationRecord]


class MessageListResponse(ChatBaseModel):
    """Response body for listing conversation messages."""

    messages: list[MessageResponse]


class SendMessageResponse(ChatBaseModel):
    """Response body containing a completed user/assistant turn."""

    conversation: ConversationResponse
    user_message: MessageResponse
    assistant_message: MessageResponse
    finish_reason: str | None = None
    blocked_reason: str | None = None
