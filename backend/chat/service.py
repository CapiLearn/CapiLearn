import logging
from decimal import Decimal
from uuid import UUID

from fastapi import status
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.schemas import CurrentUser
from backend.chat.models import Conversation, Message, utc_now
from backend.chat.repository import ChatRepository
from backend.chat.schemas import (
    ConversationListResponse,
    ConversationResponse,
    ConversationStatus,
    MessageListResponse,
    MessageResponse,
    MessageRole,
    MessageStatus,
    SendMessageResponse,
)
from backend.core.exceptions import ApiError
from backend.core.observability import (
    LLMTraceSink,
    elapsed_ms,
    get_request_id,
    log_event,
    new_request_id,
    timer_start,
)
from backend.llm.prompts import build_user_message_content
from backend.llm.schemas import (
    ChatMessage,
    ChatRole,
    LLMRequest,
    LLMResult,
    RetrievedChunk,
)
from backend.llm.service import LLMService, LLMServiceError

RECENT_RETRIEVED_CONTEXT_TURNS = 3
logger = logging.getLogger(__name__)


class ChatService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        current_user: CurrentUser,
        llm_service: LLMService,
        repository: ChatRepository | None = None,
        trace_sink: LLMTraceSink | None = None,
    ) -> None:
        self._session = session
        self._current_user = current_user
        self._llm_service = llm_service
        self._repository = repository or ChatRepository()
        self._trace_sink = trace_sink or LLMTraceSink()

    async def list_conversations(self) -> ConversationListResponse:
        conversations = await self._repository.list_conversations(
            self._session,
            user_id=self._current_user.id,
        )
        return ConversationListResponse(
            conversations=[
                self._conversation_response(conversation) for conversation in conversations
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
        now = utc_now()
        conversation.deleted_at = now
        conversation.updated_at = now
        await self._session.commit()

    async def create_conversation_message(self, content: str) -> SendMessageResponse:
        title = _title_from_content(content)
        conversation = await self._repository.create_conversation(
            self._session,
            user_id=self._current_user.id,
            title=title,
        )
        return await self._create_message(conversation=conversation, content=content, history=[])

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
        turn_started_at = timer_start()
        request_id = get_request_id() or new_request_id()
        try:
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
            _set_correlation_metadata(user_message, request_id=request_id)
            _set_correlation_metadata(assistant_message, request_id=request_id)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ApiError(
                code="message_sequence_conflict",
                message="Message ordering conflict. Please retry your request.",
                status_code=status.HTTP_409_CONFLICT,
            ) from exc

        event_fields = _chat_event_fields(
            current_user=self._current_user,
            conversation=conversation,
            user_message=user_message,
            assistant_message=assistant_message,
            request_id=request_id,
        )
        await self._trace_sink.start_chat_turn(event_fields)
        log_event(logger, "chat.turn.started", **event_fields)

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
            await self._trace_sink.record_error(failed_fields)
            await self._trace_sink.finish_chat_turn(failed_fields)
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
            blocked_fields = {
                **event_fields,
                **_provider_event_fields(result),
                "status": MessageStatus.BLOCKED.value,
                "latency_ms": latency_ms,
                "blocked_reason": assistant_message.blocked_reason,
                "input_blocked": result.input_guardrail_result.blocked,
                "output_blocked": result.output_guardrail_result.blocked,
            }
            await self._trace_sink.finish_chat_turn(blocked_fields)
            log_event(logger, "chat.turn.blocked", **blocked_fields)
        else:
            await self._save_user_retrieval(user_message, result)
            await self._mark_completed(assistant_message, result, latency_ms=latency_ms)
            completed_fields = {
                **event_fields,
                **_provider_event_fields(result),
                "status": MessageStatus.COMPLETED.value,
                "latency_ms": latency_ms,
            }
            await self._trace_sink.finish_chat_turn(completed_fields)
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
        *,
        latency_ms: int,
    ) -> None:
        message.status = MessageStatus.COMPLETED.value
        message.content = result.content
        message.latency_ms = latency_ms
        message.input_guardrail_result = result.input_guardrail_result.model_dump(
            mode="json",
            by_alias=True,
        )
        message.output_guardrail_result = result.output_guardrail_result.model_dump(
            mode="json",
            by_alias=True,
        )
        _apply_provider_response(message, result)
        _apply_legacy_estimated_cost(message, result)
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
        message.blocked_reason = reason
        message.latency_ms = latency_ms
        message.input_guardrail_result = result.input_guardrail_result.model_dump(
            mode="json",
            by_alias=True,
        )
        message.output_guardrail_result = result.output_guardrail_result.model_dump(
            mode="json",
            by_alias=True,
        )
        _apply_provider_response(message, result)
        _apply_legacy_estimated_cost(message, result)
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
        message.retrieved_context = [
            chunk.model_dump(mode="json", by_alias=True, exclude_none=True)
            for chunk in result.retrieved_context
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
        if message.role == MessageRole.USER.value and message.id in recent_user_message_ids:
            chunks = _chunks_from_stored_refs(message.retrieved_context or [])
            content = _history_user_content(content, chunks)
        history.append(ChatMessage(role=ChatRole(message.role), content=content))
    return history


def _set_correlation_metadata(message: Message, *, request_id: str) -> None:
    metadata = dict(message.extra_metadata or {})
    metadata["requestId"] = request_id
    message.extra_metadata = metadata


def _apply_provider_response(message: Message, result: LLMResult) -> None:
    provider_response = result.provider_response
    if provider_response is None:
        return
    message.finish_reason = provider_response.finish_reason
    message.prompt_tokens = provider_response.prompt_tokens
    message.completion_tokens = provider_response.completion_tokens
    message.total_tokens = provider_response.total_tokens
    message.provider_response = provider_response.raw_response


def _apply_legacy_estimated_cost(message: Message, result: LLMResult) -> None:
    component_costs = [
        component.estimated_cost_usd
        for component in result.cost_components
        if component.estimated_cost_usd is not None
    ]
    if component_costs:
        message.estimated_cost_usd = sum(component_costs, Decimal("0"))


def _original_llm_exception(exc: Exception) -> Exception:
    if isinstance(exc, LLMServiceError):
        return exc.original_exception
    return exc


def _chat_event_fields(
    *,
    current_user: CurrentUser,
    conversation: Conversation,
    user_message: Message,
    assistant_message: Message,
    request_id: str,
) -> dict:
    return {
        "request_id": request_id,
        "user_id": str(current_user.id),
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
    completed_user_messages = [
        message
        for message in messages
        if message.role == MessageRole.USER.value
        and message.status == MessageStatus.COMPLETED.value
    ]
    return {message.id for message in completed_user_messages[-RECENT_RETRIEVED_CONTEXT_TURNS:]}


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
