from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.chat.schemas import ConversationStatus, MessageStatus
from backend.core.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class Conversation(Base):
    __tablename__ = "conversation"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("user_account.id"),
        nullable=False,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ConversationStatus.ACTIVE.value,
        index=True,
    )
    model_profile_key: Mapped[str] = mapped_column(String(120), nullable=False)
    model_profile_version: Mapped[str | None] = mapped_column(String(120))
    guardrails_config_id: Mapped[str | None] = mapped_column(String(120))
    rag_index_version: Mapped[str | None] = mapped_column(String(120))
    extra_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        index=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )


class Message(Base):
    __tablename__ = "message"
    __table_args__ = (
        UniqueConstraint("conversation_id", "sequence", name="message_conversation_sequence_key"),
        Index("message_role_created_at_idx", "role", "created_at"),
        Index("message_status_created_at_idx", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversation.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("user_account.id"),
        nullable=False,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=MessageStatus.COMPLETED.value,
    )
    content: Mapped[str | None] = mapped_column(Text)
    content_parts: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    finish_reason: Mapped[str | None] = mapped_column(String(120))
    retrieved_context: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    input_guardrail_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    output_guardrail_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    blocked_reason: Mapped[str | None] = mapped_column(Text)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    provider_response: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        index=True,
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class LLMCostComponent(Base):
    __tablename__ = "llm_cost_component"
    __table_args__ = (
        Index("llm_cost_component_assistant_message_id_idx", "assistant_message_id"),
        Index(
            "llm_cost_component_conversation_created_at_idx",
            "conversation_id",
            "created_at",
        ),
        Index("llm_cost_component_created_at_idx", "created_at"),
        Index(
            "llm_cost_component_component_type_created_at_idx",
            "component_type",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("user_account.id"),
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversation.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_message_id: Mapped[UUID] = mapped_column(
        ForeignKey("message.id", ondelete="CASCADE"),
        nullable=False,
    )
    assistant_message_id: Mapped[UUID] = mapped_column(
        ForeignKey("message.id", ondelete="CASCADE"),
        nullable=False,
    )
    component_order: Mapped[int] = mapped_column(Integer, nullable=False)
    component_type: Mapped[str] = mapped_column(String(80), nullable=False)
    attempt_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    provider: Mapped[str | None] = mapped_column(String(120))
    configured_model: Mapped[str | None] = mapped_column(String(255))
    response_model: Mapped[str | None] = mapped_column(String(255))
    finish_reason: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 12))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_type: Mapped[str | None] = mapped_column(String(120))
    extra_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )
