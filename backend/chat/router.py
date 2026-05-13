from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from backend.auth.dependencies import get_current_user
from backend.chat.dependencies import ChatServiceDep
from backend.chat.schemas import (
    ConversationListResponse,
    MessageListResponse,
    SendMessageResponse,
    SendMessageRequest,
)

router = APIRouter(
    prefix="/conversations",
    tags=["conversations"],
    dependencies=[Depends(get_current_user)],
)


@router.get(
    "",
    operation_id="listConversations",
    summary="List conversations",
)
async def list_conversations(service: ChatServiceDep) -> ConversationListResponse:
    return await service.list_conversations()


@router.post(
    "",
    operation_id="createConversation",
    summary="Start a new conversation",
)
async def create_conversation(
    payload: SendMessageRequest,
    service: ChatServiceDep,
) -> SendMessageResponse:
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
    return await service.list_messages(conversation_id)


@router.post(
    "/{conversation_id}/messages",
    operation_id="createMessage",
    summary="Send a message",
)
async def create_message(
    conversation_id: UUID,
    payload: SendMessageRequest,
    service: ChatServiceDep,
) -> SendMessageResponse:
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
) -> Response:
    await service.delete_conversation(conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
