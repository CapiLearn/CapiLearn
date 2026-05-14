from datetime import UTC, datetime
from uuid import uuid4

import pytest

from backend.chat.models import Conversation, Message
from backend.chat.schemas import (
    ConversationStatus,
    CurrentUser,
    MessageRole,
    MessageStatus,
)
from backend.chat.service import ChatService
from backend.core.exceptions import ApiError
from backend.llm.schemas import (
    ChatMessage,
    ChatRole,
    GuardrailResult,
    LLMResult,
    ProviderResponse,
    RetrievedChunk,
)


@pytest.mark.asyncio
async def test_create_conversation_message_completes_assistant_message() -> None:
    user = CurrentUser(id=uuid4())
    repository = FakeChatRepository(user_id=user.id)
    llm_service = FakeLLMService(
        LLMResult(
            content="Cells are small units.",
            retrieved_context=[
                RetrievedChunk(
                    content="Cell note",
                    source_id="doc_1",
                    title="Biology Notes",
                )
            ],
            provider_response=ProviderResponse(
                content="Cells are small units.",
                finish_reason="stop",
                prompt_tokens=4,
                completion_tokens=5,
                total_tokens=9,
                raw_response={"id": "provider-response"},
            ),
        )
    )
    service = ChatService(
        session=object(),
        current_user=user,
        llm_service=llm_service,
        repository=repository,
    )

    response = await service.create_conversation_message("Explain cells.")

    assert response.conversation.title == "Explain cells."
    assert response.user_message.content == "Explain cells."
    assert response.assistant_message.content == "Cells are small units."
    assert response.assistant_message.status == MessageStatus.COMPLETED
    assert response.finish_reason == "stop"
    assert response.blocked_reason is None
    assert llm_service.requests[0].history == []
    assert repository.messages[-1].retrieved_context == [
        {
            "content": "Cell note",
            "sourceId": "doc_1",
            "title": "Biology Notes",
            "page": None,
            "url": None,
            "metadata": {},
        }
    ]
    assert repository.messages[-1].citations in (None, [])


@pytest.mark.asyncio
async def test_create_message_uses_completed_history() -> None:
    user = CurrentUser(id=uuid4())
    conversation = _conversation(user_id=user.id)
    repository = FakeChatRepository(
        user_id=user.id,
        conversations=[conversation],
        messages=[
            _message(
                conversation=conversation,
                user_id=user.id,
                sequence=1,
                role=MessageRole.USER,
                status=MessageStatus.COMPLETED,
                content="What is a cell?",
            ),
            _message(
                conversation=conversation,
                user_id=user.id,
                sequence=2,
                role=MessageRole.ASSISTANT,
                status=MessageStatus.COMPLETED,
                content="A cell is a basic unit of life.",
            ),
            _message(
                conversation=conversation,
                user_id=user.id,
                sequence=3,
                role=MessageRole.ASSISTANT,
                status=MessageStatus.FAILED,
                content="",
            ),
        ],
    )
    llm_service = FakeLLMService(
        LLMResult(
            content="Cells contain organelles.",
            provider_response=ProviderResponse(
                content="Cells contain organelles.",
                finish_reason="stop",
            ),
        )
    )
    service = ChatService(
        session=object(),
        current_user=user,
        llm_service=llm_service,
        repository=repository,
    )

    response = await service.create_message(conversation.id, "Tell me more.")

    assert response.assistant_message.content == "Cells contain organelles."
    assert llm_service.requests[0].history == [
        ChatMessage(role=ChatRole.USER, content="What is a cell?"),
        ChatMessage(role=ChatRole.ASSISTANT, content="A cell is a basic unit of life."),
    ]


@pytest.mark.asyncio
async def test_blocked_input_returns_blocked_assistant_message() -> None:
    user = CurrentUser(id=uuid4())
    repository = FakeChatRepository(user_id=user.id)
    llm_service = FakeLLMService(
        LLMResult(
            content="Input blocked.",
            input_guardrail_result=GuardrailResult(
                blocked=True,
                reason="Input blocked.",
                rail="input",
            ),
        )
    )
    service = ChatService(
        session=object(),
        current_user=user,
        llm_service=llm_service,
        repository=repository,
    )

    response = await service.create_conversation_message("unsafe")

    assert response.assistant_message.status == MessageStatus.BLOCKED
    assert response.assistant_message.content == "Input blocked."
    assert response.blocked_reason == "Input blocked."
    assert repository.messages[-1].blocked_reason == "Input blocked."


@pytest.mark.asyncio
async def test_blocked_output_returns_blocked_assistant_message() -> None:
    user = CurrentUser(id=uuid4())
    repository = FakeChatRepository(user_id=user.id)
    llm_service = FakeLLMService(
        LLMResult(
            content="Output blocked.",
            output_guardrail_result=GuardrailResult(
                blocked=True,
                reason="Output blocked.",
                rail="output",
            ),
            provider_response=ProviderResponse(
                content="Unsafe answer.",
                finish_reason="stop",
            ),
        )
    )
    service = ChatService(
        session=object(),
        current_user=user,
        llm_service=llm_service,
        repository=repository,
    )

    response = await service.create_conversation_message("safe input")

    assert response.assistant_message.status == MessageStatus.BLOCKED
    assert response.assistant_message.content == "Output blocked."
    assert response.blocked_reason == "Output blocked."


@pytest.mark.asyncio
async def test_llm_exception_marks_assistant_failed_and_raises_api_error() -> None:
    user = CurrentUser(id=uuid4())
    repository = FakeChatRepository(user_id=user.id)
    service = ChatService(
        session=object(),
        current_user=user,
        llm_service=FailingLLMService(),
        repository=repository,
    )

    with pytest.raises(ApiError) as exc_info:
        await service.create_conversation_message("Explain cells.")

    assert exc_info.value.code == "llm_unavailable"
    assert repository.messages[-1].status == MessageStatus.FAILED.value
    assert repository.messages[-1].error == {"type": "RuntimeError"}


class FakeChatRepository:
    def __init__(
        self,
        *,
        user_id,
        conversations: list[Conversation] | None = None,
        messages: list[Message] | None = None,
    ) -> None:
        self.user_id = user_id
        self.conversations = conversations or []
        self.messages = messages or []
        self.save_count = 0

    async def create_conversation(self, session, *, user_id, title):
        conversation = _conversation(user_id=user_id, title=title)
        self.conversations.append(conversation)
        return conversation

    async def get_conversation(self, session, *, conversation_id, user_id):
        for conversation in self.conversations:
            if conversation.id == conversation_id and conversation.user_id == user_id:
                return conversation
        return None

    async def list_messages(self, session, *, conversation_id, user_id):
        return [
            message
            for message in self.messages
            if message.conversation_id == conversation_id and message.user_id == user_id
        ]

    async def create_message(
        self,
        session,
        *,
        conversation,
        user_id,
        role,
        status,
        content,
    ):
        message = _message(
            conversation=conversation,
            user_id=user_id,
            sequence=len(
                [
                    item
                    for item in self.messages
                    if item.conversation_id == conversation.id
                ]
            )
            + 1,
            role=role,
            status=status,
            content=content,
        )
        self.messages.append(message)
        return message

    async def save(self, session) -> None:
        self.save_count += 1


class FakeLLMService:
    def __init__(self, result: LLMResult) -> None:
        self.result = result
        self.requests = []

    async def complete(self, request):
        self.requests.append(request)
        return self.result


class FailingLLMService:
    async def complete(self, request):
        raise RuntimeError("provider unavailable")


def _conversation(
    *,
    user_id,
    title: str | None = "Existing title",
) -> Conversation:
    now = datetime.now(UTC)
    return Conversation(
        id=uuid4(),
        user_id=user_id,
        title=title,
        status=ConversationStatus.ACTIVE.value,
        langgraph_thread_id=str(uuid4()),
        model_profile_key="model",
        created_at=now,
        updated_at=now,
    )


def _message(
    *,
    conversation: Conversation,
    user_id,
    sequence: int,
    role: MessageRole,
    status: MessageStatus,
    content: str,
) -> Message:
    return Message(
        id=uuid4(),
        conversation_id=conversation.id,
        user_id=user_id,
        sequence=sequence,
        role=role.value,
        status=status.value,
        content=content,
        created_at=datetime.now(UTC),
    )
