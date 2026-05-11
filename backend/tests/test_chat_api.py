import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import get_args
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from backend.chat.dependencies import get_chat_service
from backend.chat.events import (
    AssistantMessageCreatedPayload,
    BlockedPayload,
    ChatStreamEvent,
    ChatStreamPayloadUnion,
    CompletedPayload,
    ConversationCreatedPayload,
    DeltaPayload,
    UserMessageCreatedPayload,
    sse_event,
)
from backend.chat.schemas import (
    ConversationListResponse,
    ConversationResponse,
    ConversationStatus,
    MessageListResponse,
    MessageResponse,
    MessageRole,
    MessageStatus,
)
from backend.main import app


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_stream_openapi_responses_are_typed_event_streams() -> None:
    schema = app.openapi()
    stream_paths = [
        "/api/conversations/stream",
        "/api/conversations/{conversation_id}/messages/stream",
    ]

    for path in stream_paths:
        response = schema["paths"][path]["post"]["responses"]["200"]
        content = response["content"]
        assert set(content) == {"text/event-stream"}

        stream_schema = content["text/event-stream"]["schema"]
        assert stream_schema["discriminator"] == {"propertyName": "type"}
        assert {
            option["properties"]["type"]["const"] for option in stream_schema["oneOf"]
        } == {event.value for event in ChatStreamEvent}
        assert all("type" in option["required"] for option in stream_schema["oneOf"])


def test_event_payload_coverage() -> None:
    payload_union = get_args(ChatStreamPayloadUnion)[0]
    payload_types = [
        get_args(variant.__annotations__["type"])[0]
        for variant in get_args(payload_union)
    ]

    assert set(payload_types) == {event.value for event in ChatStreamEvent}
    assert len(payload_types) == len(set(payload_types))


def test_chat_routes_have_stable_operation_ids() -> None:
    schema = app.openapi()

    assert schema["paths"]["/api/conversations"]["get"]["operationId"] == (
        "listConversations"
    )
    assert schema["paths"]["/api/conversations/stream"]["post"]["operationId"] == (
        "createConversationStream"
    )
    assert (
        schema["paths"]["/api/conversations/{conversation_id}/messages"]["get"][
            "operationId"
        ]
        == "listMessages"
    )
    assert (
        schema["paths"]["/api/conversations/{conversation_id}/messages/stream"]["post"][
            "operationId"
        ]
        == "createMessageStream"
    )
    assert (
        schema["paths"]["/api/conversations/{conversation_id}"]["patch"]["operationId"]
        == "updateConversation"
    )
    assert (
        schema["paths"]["/api/conversations/{conversation_id}"]["delete"]["operationId"]
        == "deleteConversation"
    )


@pytest.mark.asyncio
async def test_first_message_stream_emits_lifecycle_events() -> None:
    app.dependency_overrides[get_chat_service] = lambda: FakeChatService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/conversations/stream",
            json={"content": "Explain cells."},
        )

    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert [event["event"] for event in events] == [
        ChatStreamEvent.CONVERSATION_CREATED.value,
        ChatStreamEvent.USER_MESSAGE_CREATED.value,
        ChatStreamEvent.ASSISTANT_MESSAGE_CREATED.value,
        ChatStreamEvent.DELTA.value,
        ChatStreamEvent.COMPLETED.value,
    ]
    assert [event["data"]["type"] for event in events] == [
        event["event"] for event in events
    ]


@pytest.mark.asyncio
async def test_followup_stream_surfaces_ownership_failure() -> None:
    app.dependency_overrides[get_chat_service] = lambda: MissingConversationService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            f"/api/conversations/{uuid4()}/messages/stream",
            json={"content": "Follow up."},
        )

    assert response.status_code == 404
    assert response.json()["code"] == "conversation_not_found"


@pytest.mark.asyncio
async def test_blocked_input_stream_emits_blocked_event() -> None:
    app.dependency_overrides[get_chat_service] = lambda: BlockedChatService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/conversations/stream",
            json={"content": "unsafe"},
        )

    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert events[-1]["event"] == ChatStreamEvent.BLOCKED.value
    assert events[-1]["data"]["type"] == ChatStreamEvent.BLOCKED.value
    assert events[-1]["data"]["status"] == MessageStatus.BLOCKED.value


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
        "status",
        "createdAt",
        "updatedAt",
        "lastMessagePreview",
    }
    assert set(message_payload) == {
        "id",
        "conversationId",
        "role",
        "content",
        "status",
        "citations",
        "createdAt",
    }


class FakeChatService:
    conversation_id = uuid4()
    user_message_id = uuid4()
    assistant_message_id = uuid4()
    created_at = datetime.now(UTC)

    async def stream_new_conversation(
        self, content: str
    ) -> AsyncIterator[dict[str, str]]:
        return self._stream_conversation(content)

    async def _stream_conversation(self, content: str) -> AsyncIterator[dict[str, str]]:
        yield sse_event(
            ConversationCreatedPayload(
                conversation_id=self.conversation_id,
                title="Explain cells.",
            )
        )
        yield sse_event(
            UserMessageCreatedPayload(
                message_id=self.user_message_id,
                conversation_id=self.conversation_id,
            )
        )
        yield sse_event(
            AssistantMessageCreatedPayload(
                message_id=self.assistant_message_id,
                conversation_id=self.conversation_id,
                status=MessageStatus.STREAMING.value,
            )
        )
        yield sse_event(
            DeltaPayload(
                message_id=self.assistant_message_id,
                text="Cells are small units.",
            )
        )
        yield sse_event(
            CompletedPayload(
                message_id=self.assistant_message_id,
                status=MessageStatus.COMPLETED.value,
                finish_reason="stop",
            )
        )

    async def stream_message(
        self,
        conversation_id: UUID,
        content: str,
    ) -> AsyncIterator[dict[str, str]]:
        return self._stream_conversation(content)

    async def list_conversations(self) -> ConversationListResponse:
        return ConversationListResponse(
            conversations=[
                ConversationResponse(
                    id=self.conversation_id,
                    title="Explain cells.",
                    status=ConversationStatus.ACTIVE,
                    created_at=self.created_at,
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
                    citations=[],
                    created_at=self.created_at,
                ),
            ],
        )


class MissingConversationService(FakeChatService):
    async def stream_message(
        self,
        conversation_id: UUID,
        content: str,
    ) -> AsyncIterator[dict[str, str]]:
        from backend.core.exceptions import ApiError

        raise ApiError(
            code="conversation_not_found",
            message="Conversation was not found.",
            status_code=404,
        )


class BlockedChatService(FakeChatService):
    async def stream_new_conversation(
        self, content: str
    ) -> AsyncIterator[dict[str, str]]:
        return self._stream_blocked()

    async def _stream_blocked(self) -> AsyncIterator[dict[str, str]]:
        yield sse_event(
            AssistantMessageCreatedPayload(
                message_id=self.assistant_message_id,
                conversation_id=self.conversation_id,
                status=MessageStatus.STREAMING.value,
            )
        )
        yield sse_event(
            BlockedPayload(
                message_id=self.assistant_message_id,
                status=MessageStatus.BLOCKED.value,
                reason="Blocked.",
            )
        )


def _parse_sse(body: str) -> list[dict[str, object]]:
    events = []
    body = body.replace("\r\n", "\n")
    for block in body.strip().split("\n\n"):
        event_name = None
        data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line.removeprefix("event: ")
            if line.startswith("data: "):
                data = json.loads(line.removeprefix("data: "))
        if event_name is not None and data is not None:
            events.append({"event": event_name, "data": data})
    return events
