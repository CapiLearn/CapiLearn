from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.chat.models import Conversation, LLMCostComponent, Message, utc_now
from backend.chat.schemas import ConversationStatus, MessageRole, MessageStatus
from backend.llm.schemas import LLMCostComponent as LLMCostComponentRecord


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
        model_profile_key: str,
        model_profile_version: str | None,
        guardrails_config_id: str | None,
        rag_index_version: str | None,
    ) -> Conversation:
        conversation = Conversation(
            user_id=user_id,
            title=title,
            model_profile_key=model_profile_key,
            model_profile_version=model_profile_version,
            guardrails_config_id=guardrails_config_id,
            rag_index_version=rag_index_version,
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
            .where(Message.conversation_id == conversation_id, Message.user_id == user_id)
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
            sequence=await self._next_sequence(session, conversation_id=conversation.id),
            role=role.value,
            status=status.value,
            content=content,
        )
        conversation.updated_at = utc_now()
        session.add(message)
        await session.flush()
        return message

    async def create_llm_cost_components(
        self,
        session: AsyncSession,
        *,
        components: list[LLMCostComponentRecord],
    ) -> None:
        if any(component.assistant_message_id is None for component in components):
            raise ValueError("LLM cost component requires assistant_message_id.")
        for component in components:
            session.add(
                LLMCostComponent(
                    user_id=component.user_id,
                    conversation_id=component.conversation_id,
                    user_message_id=component.user_message_id,
                    assistant_message_id=component.assistant_message_id,
                    component_order=component.component_order,
                    component_type=component.component_type,
                    attempt_index=component.attempt_index,
                    provider=component.provider,
                    configured_model=component.configured_model,
                    response_model=component.response_model,
                    finish_reason=component.finish_reason,
                    status=component.status,
                    prompt_tokens=component.prompt_tokens,
                    completion_tokens=component.completion_tokens,
                    total_tokens=component.total_tokens,
                    estimated_cost_usd=component.estimated_cost_usd,
                    latency_ms=component.latency_ms,
                    error_type=component.error_type,
                    extra_metadata=component.metadata,
                )
            )
        await session.flush()

    async def _next_sequence(self, session: AsyncSession, *, conversation_id: UUID) -> int:
        statement: Select[tuple[int | None]] = select(func.max(Message.sequence)).where(
            Message.conversation_id == conversation_id,
        )
        current = await session.scalar(statement)
        return (current or 0) + 1
