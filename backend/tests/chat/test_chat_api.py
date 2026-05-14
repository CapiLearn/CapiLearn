import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from backend.chat.dependencies import get_chat_service
from backend.chat.schemas import (
    ConversationListResponse,
    ConversationResponse,
    MessageListResponse,
    MessageResponse,
    MessageRole,
    MessageStatus,
    SendMessageResponse,
)
from backend.main import app


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_chat_openapi_uses_json_send_routes_without_streams_or_citations() -> None:
    schema = app.openapi()

    assert "/api/conversations/stream" not in schema["paths"]
    assert "/api/conversations/{conversation_id}/messages/stream" not in schema["paths"]
    assert "post" in schema["paths"]["/api/conversations"]
    assert "post" in schema["paths"]["/api/conversations/{conversation_id}/messages"]

    serialized_schema = json.dumps(schema)
    assert "text/event-stream" not in serialized_schema
    assert "citations" not in serialized_schema


def test_chat_routes_have_stable_operation_ids() -> None:
    schema = app.openapi()

    assert schema["paths"]["/api/conversations"]["get"]["operationId"] == (
        "listConversations"
    )
    assert schema["paths"]["/api/conversations"]["post"]["operationId"] == (
        "createConversation"
    )
    assert (
        schema["paths"]["/api/conversations/{conversation_id}/messages"]["get"][
            "operationId"
        ]
        == "listMessages"
    )
    assert (
        schema["paths"]["/api/conversations/{conversation_id}/messages"]["post"][
            "operationId"
        ]
        == "createMessage"
    )
    assert "patch" not in schema["paths"]["/api/conversations/{conversation_id}"]
    serialized_schema = json.dumps(schema)
    assert "updateConversation" not in serialized_schema
    assert (
        schema["paths"]["/api/conversations/{conversation_id}"]["delete"]["operationId"]
        == "deleteConversation"
    )


@pytest.mark.asyncio
async def test_create_conversation_returns_complete_message_response() -> None:
    app.dependency_overrides[get_chat_service] = lambda: FakeChatService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/conversations",
            json={"content": "Explain cells."},
        )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "conversation",
        "userMessage",
        "assistantMessage",
        "finishReason",
        "blockedReason",
    }
    assert "citations" not in payload
    assert payload["conversation"]["id"] == str(FakeChatService.conversation_id)
    assert payload["userMessage"]["role"] == MessageRole.USER.value
    assert payload["assistantMessage"]["content"] == "Cells are small units."
    assert payload["assistantMessage"]["status"] == MessageStatus.COMPLETED.value
    assert payload["finishReason"] == "stop"
    assert payload["blockedReason"] is None


@pytest.mark.asyncio
async def test_invalid_user_header_returns_401() -> None:
    app.dependency_overrides[get_chat_service] = lambda: FakeChatService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/conversations",
            headers={"X-User-Id": "not-a-uuid"},
        )

    assert response.status_code == 401
    assert response.json() == {
        "code": "invalid_user_header",
        "message": "X-User-Id must be a valid UUID.",
        "details": None,
    }


@pytest.mark.asyncio
async def test_followup_message_surfaces_ownership_failure() -> None:
    app.dependency_overrides[get_chat_service] = lambda: MissingConversationService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            f"/api/conversations/{uuid4()}/messages",
            json={"content": "Follow up."},
        )

    assert response.status_code == 404
    assert response.json()["code"] == "conversation_not_found"


@pytest.mark.asyncio
async def test_blocked_input_returns_blocked_assistant_message() -> None:
    app.dependency_overrides[get_chat_service] = lambda: BlockedChatService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/conversations",
            json={"content": "unsafe"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["assistantMessage"]["status"] == MessageStatus.BLOCKED.value
    assert payload["assistantMessage"]["content"] == "Blocked."
    assert payload["blockedReason"] == "Blocked."


@pytest.mark.asyncio
async def test_conversation_and_message_reads_are_frontend_safe() -> None:
    app.dependency_overrides[get_chat_service] = lambda: FakeChatService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        conversations = await client.get("/api/conversations")
        messages = await client.get(
            f"/api/conversations/{FakeChatService.conversation_id}/messages"
        )

    assert conversations.status_code == 200
    assert messages.status_code == 200
    conversation_payload = conversations.json()["conversations"][0]
    message_payload = messages.json()["messages"][0]
    assert set(conversation_payload) == {
        "id",
        "title",
        "updatedAt",
    }
    assert set(message_payload) == {
        "id",
        "conversationId",
        "role",
        "content",
        "status",
        "createdAt",
    }


class FakeChatService:
    conversation_id = uuid4()
    user_message_id = uuid4()
    assistant_message_id = uuid4()
    created_at = datetime.now(UTC)

    def __init__(self, *, title: str | None = "Explain cells.") -> None:
        self.title = title

    async def create_conversation_message(self, content: str) -> SendMessageResponse:
        return self._send_message_response(content=content)

    async def create_message(
        self,
        conversation_id: UUID,
        content: str,
    ) -> SendMessageResponse:
        return self._send_message_response(
            conversation_id=conversation_id,
            content=content,
        )

    async def list_conversations(self) -> ConversationListResponse:
        return ConversationListResponse(
            conversations=[
                ConversationResponse(
                    id=self.conversation_id,
                    title=self.title,
                    updated_at=self.created_at,
                ),
            ],
        )

    async def list_messages(self, conversation_id: UUID) -> MessageListResponse:
        return MessageListResponse(
            messages=[
                MessageResponse(
                    id=self.assistant_message_id,
                    conversation_id=conversation_id,
                    role=MessageRole.ASSISTANT,
                    content="Cells are small units.",
                    status=MessageStatus.COMPLETED,
                    created_at=self.created_at,
                ),
            ],
        )

    def _send_message_response(
        self,
        *,
        content: str,
        conversation_id: UUID | None = None,
        assistant_status: MessageStatus = MessageStatus.COMPLETED,
        assistant_content: str = "Cells are small units.",
        finish_reason: str | None = "stop",
        blocked_reason: str | None = None,
    ) -> SendMessageResponse:
        resolved_conversation_id = conversation_id or self.conversation_id
        return SendMessageResponse(
            conversation=ConversationResponse(
                id=resolved_conversation_id,
                title=self.title,
                updated_at=self.created_at,
            ),
            user_message=MessageResponse(
                id=self.user_message_id,
                conversation_id=resolved_conversation_id,
                role=MessageRole.USER,
                content=content,
                status=MessageStatus.COMPLETED,
                created_at=self.created_at,
            ),
            assistant_message=MessageResponse(
                id=self.assistant_message_id,
                conversation_id=resolved_conversation_id,
                role=MessageRole.ASSISTANT,
                content=assistant_content,
                status=assistant_status,
                created_at=self.created_at,
            ),
            finish_reason=finish_reason,
            blocked_reason=blocked_reason,
        )


class MissingConversationService(FakeChatService):
    async def create_message(
        self,
        conversation_id: UUID,
        content: str,
    ) -> SendMessageResponse:
        from backend.core.exceptions import ApiError

        raise ApiError(
            code="conversation_not_found",
            message="Conversation was not found.",
            status_code=404,
        )


class BlockedChatService(FakeChatService):
    async def create_conversation_message(self, content: str) -> SendMessageResponse:
        return self._send_message_response(
            content=content,
            assistant_status=MessageStatus.BLOCKED,
            assistant_content="Blocked.",
            finish_reason=None,
            blocked_reason="Blocked.",
        )
