from datetime import UTC, datetime
from uuid import UUID

from fastapi import status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.chat.models import Conversation, Message
from backend.chat.repository import ChatRepository
from backend.chat.schemas import (
    ConversationListResponse,
    ConversationResponse,
    ConversationStatus,
    CurrentUser,
    MessageListResponse,
    MessageResponse,
    MessageRole,
    MessageStatus,
    SendMessageResponse,
)
from backend.core.exceptions import ApiError
from backend.llm.schemas import (
    ChatMessage,
    ChatRole,
    LLMRequest,
    LLMResult,
    RetrievedChunk,
)
from backend.llm.service import LLMService
from backend.llm.prompts import build_user_message_content


RECENT_RETRIEVED_CONTEXT_TURNS = 3


class ChatService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        current_user: CurrentUser,
        llm_service: LLMService,
        repository: ChatRepository | None = None,
    ) -> None:
        self._session = session
        self._current_user = current_user
        self._llm_service = llm_service
        self._repository = repository or ChatRepository()

    async def list_conversations(self) -> ConversationListResponse:
        conversations = await self._repository.list_conversations(
            self._session,
            user_id=self._current_user.id,
        )
        return ConversationListResponse(
            conversations=[
                self._conversation_response(conversation)
                for conversation in conversations
            ],
        )

    async def list_messages(self, conversation_id: UUID) -> MessageListResponse:
        conversation = await self._get_owned_conversation(conversation_id)
        messages = await self._repository.list_messages(
            self._session,
            conversation_id=conversation.id,
            user_id=self._current_user.id,
        )
        return MessageListResponse(
            messages=[self._message_response(message) for message in messages],
        )

    async def delete_conversation(self, conversation_id: UUID) -> None:
        conversation = await self._get_owned_conversation(conversation_id)
        conversation.status = ConversationStatus.DELETED.value
        conversation.deleted_at = datetime.now(UTC)
        conversation.updated_at = datetime.now(UTC)
        await self._session.commit()

    async def create_conversation_message(self, content: str) -> SendMessageResponse:
        title = _title_from_content(content)
        conversation = await self._repository.create_conversation(
            self._session,
            user_id=self._current_user.id,
            title=title,
        )
        return await self._create_message(
            conversation=conversation, content=content, history=[]
        )

    async def create_message(
        self,
        conversation_id: UUID,
        content: str,
    ) -> SendMessageResponse:
        conversation = await self._get_owned_conversation(conversation_id)
        existing_messages = await self._repository.list_messages(
            self._session,
            conversation_id=conversation.id,
            user_id=self._current_user.id,
        )
        history = _history_from_messages(existing_messages)
        return await self._create_message(
            conversation=conversation,
            content=content,
            history=history,
        )

    async def _create_message(
        self,
        *,
        conversation: Conversation,
        content: str,
        history: list[ChatMessage],
    ) -> SendMessageResponse:
        user_message = await self._repository.create_message(
            self._session,
            conversation=conversation,
            user_id=self._current_user.id,
            role=MessageRole.USER,
            status=MessageStatus.COMPLETED,
            content=content,
        )
        assistant_message = await self._repository.create_message(
            self._session,
            conversation=conversation,
            user_id=self._current_user.id,
            role=MessageRole.ASSISTANT,
            status=MessageStatus.PENDING,
            content="",
        )
        await self._session.commit()
        request = LLMRequest(
            user_id=self._current_user.id,
            conversation_id=conversation.id,
            user_message_id=user_message.id,
            assistant_message_id=assistant_message.id,
            content=content,
            history=history,
        )

        try:
            result = await self._llm_service.complete(request)
        except Exception as exc:
            await self._mark_failed(assistant_message, exc)
            raise ApiError(
                code="llm_unavailable",
                message="The assistant is temporarily unavailable.",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from exc

        if (
            result.input_guardrail_result.blocked
            or result.output_guardrail_result.blocked
        ):
            await self._save_user_retrieval(user_message, result)
            await self._mark_blocked(assistant_message, result)
        else:
            await self._save_user_retrieval(user_message, result)
            await self._mark_completed(assistant_message, result)

        finish_reason = None
        if result.provider_response is not None:
            finish_reason = result.provider_response.finish_reason

        return SendMessageResponse(
            conversation=self._conversation_response(conversation),
            user_message=self._message_response(user_message),
            assistant_message=self._message_response(assistant_message),
            finish_reason=finish_reason,
            blocked_reason=assistant_message.blocked_reason,
        )

    async def _get_owned_conversation(self, conversation_id: UUID) -> Conversation:
        conversation = await self._repository.get_conversation(
            self._session,
            conversation_id=conversation_id,
            user_id=self._current_user.id,
        )
        if conversation is None:
            raise ApiError(
                code="conversation_not_found",
                message="Conversation was not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return conversation

    async def _mark_completed(
        self,
        message: Message,
        result: LLMResult,
    ) -> None:
        provider_response = result.provider_response
        message.status = MessageStatus.COMPLETED.value
        message.content = result.content
        message.input_guardrail_result = result.input_guardrail_result.model_dump(
            mode="json",
            by_alias=True,
        )
        message.output_guardrail_result = result.output_guardrail_result.model_dump(
            mode="json",
            by_alias=True,
        )
        if provider_response is not None:
            message.finish_reason = provider_response.finish_reason
            message.prompt_tokens = provider_response.prompt_tokens
            message.completion_tokens = provider_response.completion_tokens
            message.total_tokens = provider_response.total_tokens
            message.provider_response = provider_response.raw_response
        await self._session.commit()

    async def _mark_blocked(self, message: Message, result: LLMResult) -> None:
        reason = result.content
        message.status = MessageStatus.BLOCKED.value
        message.content = reason
        message.blocked_reason = reason
        message.input_guardrail_result = result.input_guardrail_result.model_dump(
            mode="json",
            by_alias=True,
        )
        message.output_guardrail_result = result.output_guardrail_result.model_dump(
            mode="json",
            by_alias=True,
        )
        await self._session.commit()

    async def _save_user_retrieval(
        self,
        message: Message,
        result: LLMResult,
    ) -> None:
        message.retrieved_context = [
            chunk.model_dump(mode="json", by_alias=True)
            for chunk in result.retrieved_context
        ]
        metadata = dict(message.extra_metadata or {})
        metadata["retrieval"] = result.retrieval_result.model_dump(
            mode="json",
            by_alias=True,
            exclude={"chunks"},
        )
        message.extra_metadata = metadata

    async def _mark_failed(self, message: Message, exc: Exception) -> None:
        message.status = MessageStatus.FAILED.value
        message.error = {"type": type(exc).__name__}
        await self._session.commit()

    def _conversation_response(
        self, conversation: Conversation
    ) -> ConversationResponse:
        return ConversationResponse(
            id=conversation.id,
            title=conversation.title,
            updated_at=conversation.updated_at,
        )

    def _message_response(self, message: Message) -> MessageResponse:
        return MessageResponse(
            id=message.id,
            conversation_id=message.conversation_id,
            role=MessageRole(message.role),
            content=message.content or "",
            status=MessageStatus(message.status),
            created_at=message.created_at,
        )


def _history_from_messages(messages: list[Message]) -> list[ChatMessage]:
    history = []
    recent_user_message_ids = _recent_user_message_ids(messages)
    for message in messages:
        if message.status != MessageStatus.COMPLETED.value:
            continue
        if message.role not in {MessageRole.USER.value, MessageRole.ASSISTANT.value}:
            continue
        content = message.content or ""
        if (
            message.role == MessageRole.USER.value
            and message.id in recent_user_message_ids
        ):
            chunks = _chunks_from_stored_refs(message.retrieved_context or [])
            content = _history_user_content(content, chunks)
        history.append(ChatMessage(role=ChatRole(message.role), content=content))
    return history


def _recent_user_message_ids(messages: list[Message]) -> set[UUID]:
    completed_user_messages = [
        message
        for message in messages
        if message.role == MessageRole.USER.value
        and message.status == MessageStatus.COMPLETED.value
    ]
    return {
        message.id
        for message in completed_user_messages[-RECENT_RETRIEVED_CONTEXT_TURNS:]
    }


def _history_user_content(content: str, chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return content
    return build_user_message_content(user_input=content, chunks=chunks)


def _chunks_from_stored_refs(chunk_refs: list[dict]) -> list[RetrievedChunk]:
    chunks = []
    for chunk_ref in chunk_refs:
        try:
            chunks.append(RetrievedChunk.model_validate(chunk_ref))
        except ValidationError:
            continue
    return chunks


def _title_from_content(content: str) -> str:
    normalized = " ".join(content.split())
    return normalized[:80] or "New conversation"
