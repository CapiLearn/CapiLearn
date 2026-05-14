from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.chat.models import Conversation, Message
from backend.chat.schemas import ConversationStatus, MessageRole, MessageStatus
from backend.llm.config import llm_settings


class ChatRepository:
    async def list_conversations(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
    ) -> list[Conversation]:
        statement = (
            select(Conversation)
            .where(
                Conversation.user_id == user_id,
                Conversation.status != ConversationStatus.DELETED.value,
            )
            .order_by(Conversation.updated_at.desc())
        )
        return list((await session.scalars(statement)).all())

    async def get_conversation(
        self,
        session: AsyncSession,
        *,
        conversation_id: UUID,
        user_id: UUID,
    ) -> Conversation | None:
        statement = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
            Conversation.status != ConversationStatus.DELETED.value,
        )
        return await session.scalar(statement)

    async def create_conversation(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        title: str | None,
    ) -> Conversation:
        conversation = Conversation(
            user_id=user_id,
            title=title,
            model_profile_key=llm_settings.model_profile_key,
            model_profile_version=llm_settings.model_profile_version,
            guardrails_config_id=llm_settings.guardrails_config_id,
            rag_index_version=llm_settings.rag_index_version,
        )
        session.add(conversation)
        await session.flush()
        return conversation

    async def list_messages(
        self,
        session: AsyncSession,
        *,
        conversation_id: UUID,
        user_id: UUID,
    ) -> list[Message]:
        statement = (
            select(Message)
            .where(
                Message.conversation_id == conversation_id, Message.user_id == user_id
            )
            .order_by(Message.sequence.asc())
        )
        return list((await session.scalars(statement)).all())

    async def create_message(
        self,
        session: AsyncSession,
        *,
        conversation: Conversation,
        user_id: UUID,
        role: MessageRole,
        status: MessageStatus,
        content: str | None,
    ) -> Message:
        message = Message(
            conversation_id=conversation.id,
            user_id=user_id,
            sequence=await self._next_sequence(
                session, conversation_id=conversation.id
            ),
            role=role.value,
            status=status.value,
            content=content,
        )
        conversation.updated_at = datetime.now(UTC)
        session.add(message)
        await session.flush()
        return message

    async def save(self, session: AsyncSession) -> None:
        await session.commit()

    async def rollback(self, session: AsyncSession) -> None:
        await session.rollback()

    async def _next_sequence(
        self, session: AsyncSession, *, conversation_id: UUID
    ) -> int:
        statement: Select[tuple[int | None]] = select(func.max(Message.sequence)).where(
            Message.conversation_id == conversation_id,
        )
        current = await session.scalar(statement)
        return (current or 0) + 1
