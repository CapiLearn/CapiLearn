from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.schemas import CurrentUser
from backend.chat.events import (
    AssistantMessageCreatedPayload,
    BlockedPayload,
    CitationsPayload,
    CompletedPayload,
    ConversationCreatedPayload,
    DeltaPayload,
    ErrorPayload,
    UserMessageCreatedPayload,
    sse_event,
)
from backend.chat.models import Conversation, Message
from backend.chat.repository import ChatRepository
from backend.chat.schemas import (
    ConversationListResponse,
    ConversationResponse,
    ConversationStatus,
    ConversationUpdateRequest,
    MessageListResponse,
    MessageResponse,
    MessageRole,
    MessageStatus,
)
from backend.core.exceptions import ApiError
from backend.llm.schemas import (
    ChatMessage,
    ChatRole,
    LLMBlocked,
    LLMDelta,
    LLMRequest,
    LLMResult,
)
from backend.llm.service import LLMService


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

    async def update_conversation(
        self,
        conversation_id: UUID,
        payload: ConversationUpdateRequest,
    ) -> ConversationResponse:
        conversation = await self._get_owned_conversation(conversation_id)
        if payload.title is not None:
            conversation.title = payload.title
        if payload.status is not None:
            conversation.status = payload.status.value
            if payload.status == ConversationStatus.ARCHIVED:
                conversation.archived_at = datetime.now(UTC)
        conversation.updated_at = datetime.now(UTC)
        await self._repository.save(self._session)
        return self._conversation_response(conversation)

    async def delete_conversation(self, conversation_id: UUID) -> None:
        conversation = await self._get_owned_conversation(conversation_id)
        conversation.status = ConversationStatus.DELETED.value
        conversation.deleted_at = datetime.now(UTC)
        conversation.updated_at = datetime.now(UTC)
        await self._repository.save(self._session)

    async def stream_new_conversation(
        self, content: str
    ) -> AsyncIterator[dict[str, str]]:
        title = _title_from_content(content)
        conversation = await self._repository.create_conversation(
            self._session,
            user_id=self._current_user.id,
            title=title,
        )
        return self._stream_message(
            conversation=conversation, content=content, history=[]
        )

    async def stream_message(
        self,
        conversation_id: UUID,
        content: str,
    ) -> AsyncIterator[dict[str, str]]:
        conversation = await self._get_owned_conversation(conversation_id)
        existing_messages = await self._repository.list_messages(
            self._session,
            conversation_id=conversation.id,
            user_id=self._current_user.id,
        )
        history = _history_from_messages(existing_messages)
        return self._stream_message(
            conversation=conversation,
            content=content,
            history=history,
        )

    async def _stream_message(
        self,
        *,
        conversation: Conversation,
        content: str,
        history: list[ChatMessage],
    ) -> AsyncIterator[dict[str, str]]:
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
            status=MessageStatus.STREAMING,
            content="",
        )
        await self._repository.save(self._session)

        yield sse_event(
            ConversationCreatedPayload(
                conversation_id=conversation.id,
                title=conversation.title,
            )
        )
        yield sse_event(
            UserMessageCreatedPayload(
                message_id=user_message.id,
                conversation_id=conversation.id,
            )
        )
        yield sse_event(
            AssistantMessageCreatedPayload(
                message_id=assistant_message.id,
                conversation_id=conversation.id,
                status=MessageStatus.STREAMING.value,
            )
        )

        accumulated_content = ""
        request = LLMRequest(
            user_id=self._current_user.id,
            conversation_id=conversation.id,
            message_id=assistant_message.id,
            content=content,
            history=history,
        )

        try:
            async for item in self._llm_service.stream(request):
                if isinstance(item, LLMDelta):
                    accumulated_content += item.text
                    yield sse_event(
                        DeltaPayload(
                            message_id=assistant_message.id,
                            text=item.text,
                        )
                    )
                elif isinstance(item, LLMBlocked):
                    await self._mark_blocked(assistant_message, item)
                    yield sse_event(
                        BlockedPayload(
                            message_id=assistant_message.id,
                            status=MessageStatus.BLOCKED.value,
                            reason=item.reason,
                        )
                    )
                    return
                elif isinstance(item, LLMResult):
                    await self._mark_completed(
                        assistant_message, item, accumulated_content
                    )
                    if item.citations:
                        yield sse_event(
                            CitationsPayload(
                                message_id=assistant_message.id,
                                citations=item.citations,
                            )
                        )
                    yield sse_event(
                        CompletedPayload(
                            message_id=assistant_message.id,
                            status=MessageStatus.COMPLETED.value,
                            finish_reason=_finish_reason(item),
                        )
                    )
                    return
        except Exception as exc:
            await self._mark_failed(assistant_message, exc)
            yield sse_event(
                ErrorPayload(
                    code="llm_unavailable",
                    message="The assistant is temporarily unavailable.",
                ),
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
        streamed_content: str,
    ) -> None:
        provider_response = result.provider_response
        message.status = MessageStatus.COMPLETED.value
        message.content = streamed_content or result.content
        message.citations = [
            citation.model_dump(mode="json", by_alias=True)
            for citation in result.citations
        ]
        message.retrieved_context = [
            chunk.model_dump(mode="json", by_alias=True)
            for chunk in result.retrieved_context
        ]
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
        await self._repository.save(self._session)

    async def _mark_blocked(self, message: Message, blocked: LLMBlocked) -> None:
        message.status = MessageStatus.BLOCKED.value
        message.content = blocked.reason
        message.blocked_reason = blocked.reason
        message.input_guardrail_result = blocked.guardrail_result.model_dump(
            mode="json",
            by_alias=True,
        )
        await self._repository.save(self._session)

    async def _mark_failed(self, message: Message, exc: Exception) -> None:
        message.status = MessageStatus.FAILED.value
        message.error = {"type": type(exc).__name__}
        await self._repository.save(self._session)

    def _conversation_response(
        self, conversation: Conversation
    ) -> ConversationResponse:
        return ConversationResponse(
            id=conversation.id,
            title=conversation.title,
            status=ConversationStatus(conversation.status),
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )

    def _message_response(self, message: Message) -> MessageResponse:
        return MessageResponse(
            id=message.id,
            conversation_id=message.conversation_id,
            role=MessageRole(message.role),
            content=message.content or "",
            status=MessageStatus(message.status),
            citations=message.citations or [],
            created_at=message.created_at,
        )


def _history_from_messages(messages: list[Message]) -> list[ChatMessage]:
    history = []
    for message in messages:
        if message.status != MessageStatus.COMPLETED.value:
            continue
        if message.role not in {MessageRole.USER.value, MessageRole.ASSISTANT.value}:
            continue
        history.append(
            ChatMessage(role=ChatRole(message.role), content=message.content or "")
        )
    return history


def _title_from_content(content: str) -> str:
    normalized = " ".join(content.split())
    return normalized[:80] or "New conversation"


def _finish_reason(result: LLMResult) -> str | None:
    if result.provider_response is None:
        return None
    return result.provider_response.finish_reason
