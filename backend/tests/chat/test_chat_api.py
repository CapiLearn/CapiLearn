import json
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from backend.auth.dependencies import (
    CurrentUserDep,
    get_current_user,
)
from backend.auth.schemas import CurrentUser, UserRole
from backend.chat.dependencies import get_chat_service, get_rag_retrieval_provider
from backend.chat.schemas import (
    ConversationListResponse,
    ConversationResponse,
    MessageListResponse,
    MessageResponse,
    MessageRole,
    MessageStatus,
    SendMessageResponse,
)
from backend.core.database import get_db
from backend.core.rate_limiting import (
    CHAT_MESSAGE_RATE_LIMIT,
    RATE_LIMITED_MESSAGE,
    limiter,
)
from backend.main import app
from backend.rag.schemas import RetrievalResult


@pytest.fixture(autouse=True)
def clear_overrides():
    limiter.reset()
    yield
    app.dependency_overrides.clear()
    limiter.reset()


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

    assert schema["paths"]["/api/conversations"]["get"]["operationId"] == ("listConversations")
    assert schema["paths"]["/api/conversations"]["post"]["operationId"] == ("createConversation")
    assert (
        schema["paths"]["/api/conversations/{conversation_id}/messages"]["get"]["operationId"]
        == "listMessages"
    )
    assert (
        schema["paths"]["/api/conversations/{conversation_id}/messages"]["post"]["operationId"]
        == "createMessage"
    )
    assert "patch" not in schema["paths"]["/api/conversations/{conversation_id}"]
    serialized_schema = json.dumps(schema)
    assert "updateConversation" not in serialized_schema
    assert (
        schema["paths"]["/api/conversations/{conversation_id}"]["delete"]["operationId"]
        == "deleteConversation"
    )


def _authorize(
    role: UserRole = UserRole.STUDENT,
    *,
    current_user_factory: Callable[[], CurrentUser] | None = None,
) -> None:
    async def override() -> CurrentUser:
        if current_user_factory is not None:
            return current_user_factory()
        return _current_user(role)

    app.dependency_overrides[get_current_user] = override


def _current_user(role: UserRole = UserRole.STUDENT) -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        clerk_id=f"user_{role.value}_{uuid4().hex}",
        display_name="Test User",
        role=role,
    )


def _override_chat_service(service: "FakeChatService") -> None:
    async def override(_: CurrentUserDep) -> FakeChatService:
        return service

    app.dependency_overrides[get_chat_service] = override


@pytest.mark.asyncio
async def test_create_conversation_returns_complete_message_response() -> None:
    _authorize()
    _override_chat_service(FakeChatService())

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
async def test_old_user_header_is_not_trusted() -> None:
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
        "code": "auth_required",
        "message": "Authentication is required.",
        "details": None,
    }


@pytest.mark.asyncio
async def test_chat_routes_pass_current_user_to_chat_service(monkeypatch) -> None:
    user_id = uuid4()
    current_user = CurrentUser(
        id=user_id,
        clerk_id="user_chat_existing",
        display_name="Stored User",
        role=UserRole.STUDENT,
    )
    session = FakeSession()
    captured = {}
    app.dependency_overrides[get_db] = _fake_db_override(session)
    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_rag_retrieval_provider] = lambda: FakeRetrievalProvider()

    async def list_conversations(self, session_arg, *, user_id):
        captured["session"] = session_arg
        captured["user_id"] = user_id
        return []

    monkeypatch.setattr(
        "backend.chat.repository.ChatRepository.list_conversations",
        list_conversations,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/conversations")

    assert response.status_code == 200
    assert response.json() == {"conversations": []}
    assert captured == {
        "session": session,
        "user_id": user_id,
    }


@pytest.mark.asyncio
async def test_followup_message_surfaces_ownership_failure() -> None:
    _authorize()
    _override_chat_service(MissingConversationService())

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
    _authorize()
    _override_chat_service(BlockedChatService())

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
async def test_user_can_send_ten_chat_messages_per_minute() -> None:
    user = _current_user()
    service = CountingChatService()
    _authorize(current_user_factory=lambda: user)
    _override_chat_service(service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        responses = [
            await client.post(
                "/api/conversations",
                json={"content": f"Message {index}"},
            )
            for index in range(10)
        ]

    assert [response.status_code for response in responses] == [200] * 10
    assert service.create_conversation_calls == 10
    assert service.create_message_calls == 0


@pytest.mark.asyncio
async def test_eleventh_chat_message_returns_429_without_calling_service() -> None:
    user = _current_user()
    service = CountingChatService()
    _authorize(current_user_factory=lambda: user)
    _override_chat_service(service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        for index in range(10):
            response = await client.post(
                "/api/conversations",
                json={"content": f"Message {index}"},
            )
            assert response.status_code == 200

        blocked_response = await client.post(
            "/api/conversations",
            json={"content": "Blocked message"},
        )

    assert blocked_response.status_code == 429
    assert blocked_response.json() == {
        "code": "rate_limited",
        "message": RATE_LIMITED_MESSAGE,
        "details": {"limit": CHAT_MESSAGE_RATE_LIMIT},
    }
    assert service.create_conversation_calls == 10
    assert service.create_message_calls == 0


@pytest.mark.asyncio
async def test_chat_send_routes_share_user_rate_limit_bucket() -> None:
    user = _current_user()
    service = CountingChatService()
    _authorize(current_user_factory=lambda: user)
    _override_chat_service(service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        for index in range(5):
            response = await client.post(
                "/api/conversations",
                json={"content": f"New conversation {index}"},
            )
            assert response.status_code == 200

        for index in range(5):
            response = await client.post(
                f"/api/conversations/{FakeChatService.conversation_id}/messages",
                json={"content": f"Follow up {index}"},
            )
            assert response.status_code == 200

        blocked_response = await client.post(
            f"/api/conversations/{FakeChatService.conversation_id}/messages",
            json={"content": "One too many"},
        )

    assert blocked_response.status_code == 429
    assert service.create_conversation_calls == 5
    assert service.create_message_calls == 5


@pytest.mark.asyncio
async def test_different_users_have_separate_chat_rate_limit_buckets() -> None:
    current_user = {"user": _current_user()}
    second_user = _current_user()
    service = CountingChatService()
    _authorize(current_user_factory=lambda: current_user["user"])
    _override_chat_service(service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        for index in range(10):
            response = await client.post(
                "/api/conversations",
                json={"content": f"First user message {index}"},
            )
            assert response.status_code == 200

        current_user["user"] = second_user
        response = await client.post(
            "/api/conversations",
            json={"content": "Second user message"},
        )

    assert response.status_code == 200
    assert service.create_conversation_calls == 11
    assert service.create_message_calls == 0


@pytest.mark.asyncio
async def test_non_send_chat_endpoints_are_not_limited_by_message_limiter() -> None:
    user = _current_user()
    service = CountingChatService()
    _authorize(current_user_factory=lambda: user)
    _override_chat_service(service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        for index in range(10):
            response = await client.post(
                "/api/conversations",
                json={"content": f"Message {index}"},
            )
            assert response.status_code == 200

        conversations = await client.get("/api/conversations")
        messages = await client.get(
            f"/api/conversations/{FakeChatService.conversation_id}/messages"
        )
        delete_response = await client.delete(
            f"/api/conversations/{FakeChatService.conversation_id}"
        )

    assert conversations.status_code == 200
    assert messages.status_code == 200
    assert delete_response.status_code == 204


@pytest.mark.asyncio
async def test_conversation_and_message_reads_are_frontend_safe() -> None:
    _authorize()
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


@pytest.mark.asyncio
async def test_delete_conversation_returns_empty_204_response() -> None:
    _authorize()
    service = FakeChatService()
    app.dependency_overrides[get_chat_service] = lambda: service

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.delete(f"/api/conversations/{FakeChatService.conversation_id}")

    assert response.status_code == 204
    assert response.content == b""
    assert service.deleted_conversation_id == FakeChatService.conversation_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    [UserRole.STUDENT, UserRole.INSTRUCTOR, UserRole.ADMIN],
)
async def test_chat_routes_accept_authenticated_roles(role: UserRole) -> None:
    _authorize(role)
    app.dependency_overrides[get_chat_service] = lambda: FakeChatService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/conversations")

    assert response.status_code == 200


class FakeChatService:
    conversation_id = uuid4()
    user_message_id = uuid4()
    assistant_message_id = uuid4()
    created_at = datetime.now(UTC)

    def __init__(self, *, title: str | None = "Explain cells.") -> None:
        self.title = title
        self.deleted_conversation_id: UUID | None = None

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

    async def delete_conversation(self, conversation_id: UUID) -> None:
        self.deleted_conversation_id = conversation_id

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


class CountingChatService(FakeChatService):
    def __init__(self, *, title: str | None = "Explain cells.") -> None:
        super().__init__(title=title)
        self.create_conversation_calls = 0
        self.create_message_calls = 0

    async def create_conversation_message(self, content: str) -> SendMessageResponse:
        self.create_conversation_calls += 1
        return await super().create_conversation_message(content)

    async def create_message(
        self,
        conversation_id: UUID,
        content: str,
    ) -> SendMessageResponse:
        self.create_message_calls += 1
        return await super().create_message(conversation_id, content)


class FakeRetrievalProvider:
    async def retrieve(self, query, *, user_id, conversation_id, user_message_id):
        return RetrievalResult(chunks=[])


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


def _fake_db_override(session):
    async def override():
        yield session

    return override


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class BlockedChatService(FakeChatService):
    async def create_conversation_message(self, content: str) -> SendMessageResponse:
        return self._send_message_response(
            content=content,
            assistant_status=MessageStatus.BLOCKED,
            assistant_content="Blocked.",
            finish_reason=None,
            blocked_reason="Blocked.",
        )
