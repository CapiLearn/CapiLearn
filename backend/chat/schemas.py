from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

MAX_MESSAGE_CONTENT_LENGTH = 8000


class ChatBaseModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class ConversationStatus(StrEnum):
    ACTIVE = "active"
    DELETED = "deleted"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    CONTEXT = "context"


class MessageStatus(StrEnum):
    PENDING = "pending"
    STREAMING = "streaming"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


class SendMessageRequest(ChatBaseModel):
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CONTENT_LENGTH)


class ConversationUpdateRequest(ChatBaseModel):
    title: str | None = Field(default=None, max_length=160)


class ConversationResponse(ChatBaseModel):
    id: UUID
    title: str | None
    updated_at: datetime
    last_message_preview: str | None = None


class ConversationListResponse(ChatBaseModel):
    conversations: list[ConversationResponse]


class MessageResponse(ChatBaseModel):
    id: UUID
    conversation_id: UUID
    role: MessageRole
    content: str
    status: MessageStatus
    created_at: datetime


class MessageListResponse(ChatBaseModel):
    messages: list[MessageResponse]


class SendMessageResponse(ChatBaseModel):
    conversation: ConversationResponse
    user_message: MessageResponse
    assistant_message: MessageResponse
    finish_reason: str | None = None
    blocked_reason: str | None = None
