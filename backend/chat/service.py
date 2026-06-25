"""Application service for persisted chat conversations and LLM turns."""

import logging
from uuid import UUID

from fastapi import status
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.chat.models import Conversation, Message, utc_now
from backend.chat.repository import ChatRepository, MessageSequenceConflictError
from backend.chat.schemas import (
    ConversationListResponse,
    ConversationResponse,
    ConversationStatus,
    MessageListResponse,
    MessageResponse,
    MessageRole,
    MessageStatus,
    SendMessageResponse,
    StoredRagHistoryContext,
)
from backend.core.citations import CitationRecord
from backend.core.exceptions import ApiError
from backend.core.observability import (
    LLMTraceOperation,
    LLMTraceSink,
    NoopLLMTraceSink,
    elapsed_ms,
    get_request_id,
    log_event,
    new_request_id,
    timer_start,
)
from backend.llm.config import llm_settings
from backend.llm.prompts import build_history_user_message_content
from backend.llm.schemas import (
    ChatMessage,
    ChatRole,
    LLMRequest,
    LLMResult,
)
from backend.llm.service import LLMService, LLMServiceError
from backend.rag.citations import citation_heading, validate_cited_response
from backend.rag.config import rag_settings
from backend.rag.schemas import RetrievedChunk

RECENT_RETRIEVED_CONTEXT_TURNS = 3
logger = logging.getLogger(__name__)


class ChatService:
    """Coordinate chat persistence, retrieval context, LLM calls, and trace events."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        user_id: UUID,
        llm_service: LLMService,
        repository: ChatRepository | None = None,
        trace_sink: LLMTraceSink | None = None,
    ) -> None:
        self._session = session
        self._user_id = user_id
        self._llm_service = llm_service
        self._repository = repository or ChatRepository()
        self._trace_sink = trace_sink or NoopLLMTraceSink()

    async def list_conversations(self) -> ConversationListResponse:
        """List non-deleted conversations owned by the current user."""
        conversations = await self._repository.list_conversations(
            self._session,
            user_id=self._user_id,
        )
        return ConversationListResponse(
            conversations=[
                self._conversation_response(conversation) for conversation in conversations
            ],
        )

    async def list_messages(self, conversation_id: UUID) -> MessageListResponse:
        """List messages for a conversation owned by the current user."""
        conversation = await self._get_owned_conversation(conversation_id)
        messages = await self._repository.list_messages(
            self._session,
            conversation_id=conversation.id,
            user_id=self._user_id,
        )
        return MessageListResponse(
            messages=[self._message_response(message) for message in messages],
        )

    async def delete_conversation(self, conversation_id: UUID) -> None:
        """Soft-delete a conversation owned by the current user."""
        conversation = await self._get_owned_conversation(conversation_id)
        conversation.status = ConversationStatus.DELETED.value
        now = utc_now()
        conversation.deleted_at = now
        conversation.updated_at = now
        await self._session.commit()

    async def create_conversation_message(self, content: str) -> SendMessageResponse:
        """Create a new conversation and send its first user message."""
        title = _title_from_content(content)
        conversation = await self._repository.create_conversation(
            self._session,
            user_id=self._user_id,
            title=title,
            model_profile_key=llm_settings.model_profile_key,
            model_profile_version=llm_settings.model_profile_version,
            guardrails_config_id=llm_settings.guardrails_config_id,
            rag_index_version=rag_settings.index_version,
        )
        return await self._create_message(conversation=conversation, content=content, history=[])

    async def create_message(
        self,
        conversation_id: UUID,
        content: str,
    ) -> SendMessageResponse:
        """Send a user message in an existing conversation owned by the current user."""
        conversation = await self._get_owned_conversation(conversation_id)
        existing_messages = await self._repository.list_messages(
            self._session,
            conversation_id=conversation.id,
            user_id=self._user_id,
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
        """Persist a user/assistant turn, complete it with the LLM, and record outcomes."""
        turn_started_at = timer_start()
        request_id = get_request_id() or new_request_id()
        try:
            user_message, assistant_message = await self._repository.create_turn_messages(
                self._session,
                conversation=conversation,
                user_id=self._user_id,
                content=content,
            )
            await self._session.commit()
        except MessageSequenceConflictError as exc:
            await self._session.rollback()
            raise ApiError(
                code="message_sequence_conflict",
                message="Message ordering conflict. Please retry your request.",
                status_code=status.HTTP_409_CONFLICT,
            ) from exc
        except IntegrityError:
            await self._session.rollback()
            raise

        event_fields = _chat_event_fields(
            user_id=self._user_id,
            conversation=conversation,
            user_message=user_message,
            assistant_message=assistant_message,
            request_id=request_id,
        )
        await self._trace_sink.record(LLMTraceOperation.START_CHAT_TURN, event_fields)
        log_event(logger, "chat.turn.started", **event_fields)

        request = LLMRequest(
            user_id=self._user_id,
            conversation_id=conversation.id,
            user_message_id=user_message.id,
            assistant_message_id=assistant_message.id,
            content=content,
            history=history,
        )

        try:
            result = await self._llm_service.complete(request)
        except Exception as exc:
            # Persist the assistant placeholder as failed before surfacing provider errors.
            latency_ms = elapsed_ms(turn_started_at)
            original_exc = _original_llm_exception(exc)
            cost_components = exc.cost_components if isinstance(exc, LLMServiceError) else []
            await self._mark_failed(
                assistant_message,
                original_exc,
                latency_ms=latency_ms,
                cost_components=cost_components,
            )
            failed_fields = {
                **event_fields,
                "status": MessageStatus.FAILED.value,
                "latency_ms": latency_ms,
                "error_type": type(original_exc).__name__,
            }
            await self._trace_sink.record(LLMTraceOperation.RECORD_ERROR, failed_fields)
            await self._trace_sink.record(LLMTraceOperation.FINISH_CHAT_TURN, failed_fields)
            log_event(logger, "chat.turn.failed", level=logging.ERROR, **failed_fields)
            raise ApiError(
                code="llm_unavailable",
                message="The assistant is temporarily unavailable.",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from exc

        latency_ms = elapsed_ms(turn_started_at)
        if result.input_guardrail_result.blocked or result.output_guardrail_result.blocked:
            await self._save_user_retrieval(user_message, result)
            await self._mark_blocked(assistant_message, result, latency_ms=latency_ms)
            _warn_missing_provider_response(
                result,
                event_fields=event_fields,
                status=MessageStatus.BLOCKED,
            )
            blocked_fields = {
                **event_fields,
                **_provider_event_fields(result),
                "status": MessageStatus.BLOCKED.value,
                "latency_ms": latency_ms,
                "blocked_reason": assistant_message.blocked_reason,
                "input_blocked": result.input_guardrail_result.blocked,
                "output_blocked": result.output_guardrail_result.blocked,
            }
            await self._trace_sink.record(LLMTraceOperation.FINISH_CHAT_TURN, blocked_fields)
            log_event(logger, "chat.turn.blocked", **blocked_fields)
        else:
            await self._save_user_retrieval(user_message, result)
            await self._mark_completed(assistant_message, result, latency_ms=latency_ms)
            _warn_missing_provider_response(
                result,
                event_fields=event_fields,
                status=MessageStatus.COMPLETED,
            )
            completed_fields = {
                **event_fields,
                **_provider_event_fields(result),
                "status": MessageStatus.COMPLETED.value,
                "latency_ms": latency_ms,
            }
            await self._trace_sink.record(LLMTraceOperation.FINISH_CHAT_TURN, completed_fields)
            log_event(logger, "chat.turn.completed", **completed_fields)

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
        """Return a visible conversation or raise the API-level not-found error."""
        conversation = await self._repository.get_conversation(
            self._session,
            conversation_id=conversation_id,
            user_id=self._user_id,
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
        *,
        latency_ms: int,
    ) -> None:
        validated_citations = validate_cited_response(
            result.content,
            result.retrieved_context,
        )
        message.status = MessageStatus.COMPLETED.value
        message.content = validated_citations.content
        message.citations = [
            citation.model_dump(mode="json", by_alias=True)
            for citation in validated_citations.citations
        ]
        message.latency_ms = latency_ms
        await self._repository.create_llm_cost_components(
            self._session,
            components=result.cost_components,
        )
        await self._session.commit()

    async def _mark_blocked(
        self,
        message: Message,
        result: LLMResult,
        *,
        latency_ms: int,
    ) -> None:
        reason = result.content
        message.status = MessageStatus.BLOCKED.value
        message.content = reason
        message.citations = []
        message.blocked_reason = reason
        message.latency_ms = latency_ms
        await self._repository.create_llm_cost_components(
            self._session,
            components=result.cost_components,
        )
        await self._session.commit()

    async def _save_user_retrieval(
        self,
        message: Message,
        result: LLMResult,
    ) -> None:
        message.history_context = [
            context.model_dump(mode="json", by_alias=True)
            for context in _stored_rag_context_from_chunks(result.retrieved_context)
        ]

    async def _mark_failed(
        self,
        message: Message,
        exc: Exception,
        *,
        latency_ms: int,
        cost_components=None,
    ) -> None:
        message.status = MessageStatus.FAILED.value
        message.citations = []
        message.latency_ms = latency_ms
        message.error = {"type": type(exc).__name__}
        await self._repository.create_llm_cost_components(
            self._session,
            components=cost_components or [],
        )
        await self._session.commit()

    def _conversation_response(self, conversation: Conversation) -> ConversationResponse:
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
            content=_message_content_for_response(message),
            status=MessageStatus(message.status),
            created_at=message.created_at,
            citations=_message_citations_for_response(message),
        )


def _history_from_messages(messages: list[Message]) -> list[ChatMessage]:
    """Build LLM history from completed chat messages and recent stored RAG context."""
    history = []
    recent_user_message_ids = _recent_user_message_ids(messages)
    for message in messages:
        if message.status != MessageStatus.COMPLETED.value:
            continue
        if message.role not in {MessageRole.USER.value, MessageRole.ASSISTANT.value}:
            continue
        content = _required_message_content(message)
        if message.role == MessageRole.USER.value:
            contexts = []
            if message.id in recent_user_message_ids:
                # Each completed user message stores its own retrieval context, but
                # only the last RECENT_RETRIEVED_CONTEXT_TURNS user turns replay it.
                contexts = [
                    context.model_dump(mode="json", by_alias=True)
                    for context in _stored_rag_context_from_data(message.history_context or [])
                ]
            content = build_history_user_message_content(
                user_input=content,
                contexts=contexts,
            )
        history.append(ChatMessage(role=ChatRole(message.role), content=content))
    return history


def _message_content_for_response(message: Message) -> str:
    """Return response-safe content for messages that may still be pending or failed."""
    if message.content is not None:
        return message.content

    role = MessageRole(message.role)
    status = MessageStatus(message.status)
    if role == MessageRole.ASSISTANT and status in {
        MessageStatus.PENDING,
        MessageStatus.FAILED,
    }:
        return ""

    return _required_message_content(message)


def _message_citations_for_response(message: Message) -> list[CitationRecord]:
    """Decode persisted citation payloads into API citation records."""
    if message.citations is None:
        raise ValueError(
            "Persisted chat message is missing required citations "
            f"(message_id={message.id}, role={message.role}, status={message.status})"
        )

    return [CitationRecord.model_validate_wire(citation) for citation in message.citations]


def _required_message_content(message: Message) -> str:
    """Return persisted message content or raise when the row violates chat invariants."""
    if message.content is not None:
        return message.content

    raise ValueError(
        "Persisted chat message is missing required content "
        f"(message_id={message.id}, role={message.role}, status={message.status})"
    )


def _warn_missing_provider_response(
    result: LLMResult,
    *,
    event_fields: dict,
    status: MessageStatus,
) -> None:
    if result.provider_response is not None:
        return

    log_event(
        logger,
        "chat.turn.provider_response_missing",
        level=logging.WARNING,
        **event_fields,
        status=status.value,
    )


def _original_llm_exception(exc: Exception) -> Exception:
    if isinstance(exc, LLMServiceError):
        return exc.original_exception
    return exc


def _chat_event_fields(
    *,
    user_id: UUID,
    conversation: Conversation,
    user_message: Message,
    assistant_message: Message,
    request_id: str,
) -> dict:
    return {
        "request_id": request_id,
        "user_id": str(user_id),
        "conversation_id": str(conversation.id),
        "user_message_id": str(user_message.id),
        "assistant_message_id": str(assistant_message.id),
        "model_profile_key": conversation.model_profile_key,
        "model_profile_version": conversation.model_profile_version,
        "guardrails_config_id": conversation.guardrails_config_id,
        "rag_index_version": conversation.rag_index_version,
    }


def _provider_event_fields(result: LLMResult) -> dict:
    provider_response = result.provider_response
    if provider_response is None:
        return {}
    return {
        "model": provider_response.model,
        "finish_reason": provider_response.finish_reason,
        "prompt_tokens": provider_response.prompt_tokens,
        "completion_tokens": provider_response.completion_tokens,
        "total_tokens": provider_response.total_tokens,
        "provider_latency_ms": provider_response.latency_ms,
    }


def _recent_user_message_ids(messages: list[Message]) -> set[UUID]:
    """Return the last RECENT_RETRIEVED_CONTEXT_TURNS completed user-message IDs."""
    completed_user_messages = [
        message
        for message in messages
        if message.role == MessageRole.USER.value
        and message.status == MessageStatus.COMPLETED.value
    ]
    return {message.id for message in completed_user_messages[-RECENT_RETRIEVED_CONTEXT_TURNS:]}


def _stored_rag_context_from_chunks(
    chunks: list[RetrievedChunk],
) -> list[StoredRagHistoryContext]:
    return [
        StoredRagHistoryContext(
            heading=citation_heading(chunk.metadata or {}),
            content=chunk.content,
        )
        for chunk in chunks
    ]


def _stored_rag_context_from_data(
    context_refs: list[dict],
) -> list[StoredRagHistoryContext]:
    """Validate stored RAG history context loaded from message JSON."""
    contexts = []
    for context_ref in context_refs:
        try:
            contexts.append(StoredRagHistoryContext.model_validate(context_ref))
        except (TypeError, ValidationError) as exc:
            raise ValueError("Stored history context is malformed") from exc
    return contexts


def _title_from_content(content: str) -> str:
    normalized = " ".join(content.split())
    return normalized[:80] or "New conversation"
