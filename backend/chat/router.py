from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sse_starlette import EventSourceResponse

from backend.auth.dependencies import get_current_user
from backend.chat.dependencies import ChatServiceDep
from backend.chat.events import CHAT_STREAM_RESPONSE
from backend.chat.schemas import (
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdateRequest,
    MessageListResponse,
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
    "/stream",
    operation_id="createConversationStream",
    summary="Start a new conversation stream",
    response_class=EventSourceResponse,
    responses=CHAT_STREAM_RESPONSE,
)
async def create_conversation_stream(
    payload: SendMessageRequest,
    service: ChatServiceDep,
) -> EventSourceResponse:
    return EventSourceResponse(await service.stream_new_conversation(payload.content))


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
    "/{conversation_id}/messages/stream",
    operation_id="createMessageStream",
    summary="Send a message with streaming response",
    response_class=EventSourceResponse,
    responses=CHAT_STREAM_RESPONSE,
)
async def create_message_stream(
    conversation_id: UUID,
    payload: SendMessageRequest,
    service: ChatServiceDep,
) -> EventSourceResponse:
    return EventSourceResponse(
        await service.stream_message(conversation_id, payload.content)
    )


@router.patch(
    "/{conversation_id}",
    operation_id="updateConversation",
    summary="Update a conversation",
)
async def update_conversation(
    conversation_id: UUID,
    payload: ConversationUpdateRequest,
    service: ChatServiceDep,
) -> ConversationResponse:
    return await service.update_conversation(conversation_id, payload)


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
