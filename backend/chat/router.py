"""FastAPI routes for conversation and message operations."""

from uuid import UUID

from fastapi import APIRouter, Request, status

from backend.chat.dependencies import ChatRateLimitUserDep, ChatServiceDep
from backend.chat.schemas import (
    ConversationListResponse,
    MessageListResponse,
    SendMessageRequest,
    SendMessageResponse,
)
from backend.core.rate_limiting import (
    CHAT_MESSAGE_RATE_LIMIT,
    CHAT_MESSAGE_RATE_LIMIT_SCOPE,
    limiter,
)

router = APIRouter(
    prefix="/conversations",
    tags=["conversations"],
)


@router.get(
    "",
    operation_id="listConversations",
    summary="List conversations",
)
async def list_conversations(service: ChatServiceDep) -> ConversationListResponse:
    """Return conversations visible to the authenticated student."""
    return await service.list_conversations()


@router.post(
    "",
    operation_id="createConversation",
    summary="Start a new conversation",
)
@limiter.shared_limit(CHAT_MESSAGE_RATE_LIMIT, scope=CHAT_MESSAGE_RATE_LIMIT_SCOPE)
async def create_conversation(
    request: Request,
    payload: SendMessageRequest,
    rate_limit_user: ChatRateLimitUserDep,
    service: ChatServiceDep,
) -> SendMessageResponse:
    """Start a new conversation with an initial user message."""
    return await service.create_conversation_message(payload.content)


@router.get(
    "/{conversation_id}/messages",
    operation_id="listMessages",
    summary="List conversation messages",
)
async def list_messages(
    conversation_id: UUID,
    service: ChatServiceDep,
) -> MessageListResponse:
    """Return messages for a conversation visible to the authenticated student."""
    return await service.list_messages(conversation_id)


@router.post(
    "/{conversation_id}/messages",
    operation_id="createMessage",
    summary="Send a message",
)
@limiter.shared_limit(CHAT_MESSAGE_RATE_LIMIT, scope=CHAT_MESSAGE_RATE_LIMIT_SCOPE)
async def create_message(
    request: Request,
    conversation_id: UUID,
    payload: SendMessageRequest,
    rate_limit_user: ChatRateLimitUserDep,
    service: ChatServiceDep,
) -> SendMessageResponse:
    """Send a message in an existing conversation."""
    return await service.create_message(conversation_id, payload.content)


@router.delete(
    "/{conversation_id}",
    operation_id="deleteConversation",
    summary="Delete a conversation",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_conversation(
    conversation_id: UUID,
    service: ChatServiceDep,
) -> None:
    """Soft-delete a conversation visible to the authenticated student."""
    await service.delete_conversation(conversation_id)
