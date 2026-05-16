from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

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
    RetrievalResult,
    RetrievedChunk,
)


@pytest.mark.asyncio
async def test_create_conversation_message_completes_assistant_message() -> None:
    user = CurrentUser(id=uuid4())
    session = FakeSession()
    repository = FakeChatRepository(user_id=user.id)
    llm_service = FakeLLMService(
        LLMResult(
            content="Cells are small units.",
            retrieval_result=RetrievalResult(),
            retrieved_context=[
                RetrievedChunk(
                    content="Cell note",
                    metadata={"source_id": "doc_1", "title": "Biology Notes"},
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
        session=session,
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
    assert session.commit_count == 2
    assert repository.messages[0].retrieved_context == [
        {
            "content": "Cell note",
            "metadata": {"source_id": "doc_1", "title": "Biology Notes"},
        }
    ]
    assert repository.messages[0].extra_metadata == {}
    assert repository.messages[-1].retrieved_context in (None, [])
    assert repository.messages[-1].citations in (None, [])


@pytest.mark.asyncio
async def test_create_message_uses_completed_history() -> None:
    user = CurrentUser(id=uuid4())
    session = FakeSession()
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
        session=session,
        current_user=user,
        llm_service=llm_service,
        repository=repository,
    )

    response = await service.create_message(conversation.id, "Tell me more.")

    assert response.assistant_message.content == "Cells contain organelles."
    assert session.commit_count == 2
    assert llm_service.requests[0].history == [
        ChatMessage(role=ChatRole.USER, content="What is a cell?"),
        ChatMessage(role=ChatRole.ASSISTANT, content="A cell is a basic unit of life."),
    ]


@pytest.mark.asyncio
async def test_create_message_adds_stored_context_to_recent_user_history() -> None:
    user = CurrentUser(id=uuid4())
    session = FakeSession()
    conversation = _conversation(user_id=user.id)
    messages = []
    for index in range(1, 6):
        messages.append(
            _message(
                conversation=conversation,
                user_id=user.id,
                sequence=(index * 2) - 1,
                role=MessageRole.USER,
                status=MessageStatus.COMPLETED,
                content=f"Question {index}?",
                retrieved_context=[
                    {
                        "content": f"Stored note for chunk_{index}",
                        "metadata": {
                            "source_id": "doc_1",
                            "title": "Biology Notes",
                            "page": index,
                        },
                    }
                ],
            )
        )
        messages.append(
            _message(
                conversation=conversation,
                user_id=user.id,
                sequence=index * 2,
                role=MessageRole.ASSISTANT,
                status=MessageStatus.COMPLETED,
                content=f"Answer {index}.",
            )
        )
    repository = FakeChatRepository(
        user_id=user.id,
        conversations=[conversation],
        messages=messages,
    )
    llm_service = FakeLLMService(
        LLMResult(
            content="Follow-up answer.",
            provider_response=ProviderResponse(content="Follow-up answer."),
        )
    )
    service = ChatService(
        session=session,
        current_user=user,
        llm_service=llm_service,
        repository=repository,
    )

    await service.create_message(conversation.id, "Follow up.")

    history = llm_service.requests[0].history
    user_history = [message for message in history if message.role == ChatRole.USER]
    assert user_history[0].content == "Question 1?"
    assert user_history[1].content == "Question 2?"
    assert "<retrieved_context>" in user_history[2].content
    assert "Stored note for chunk_3" in user_history[2].content
    assert "<retrieved_context>" in user_history[3].content
    assert "Stored note for chunk_4" in user_history[3].content
    assert "<retrieved_context>" in user_history[4].content
    assert "Stored note for chunk_5" in user_history[4].content
    assert ChatMessage(role=ChatRole.ASSISTANT, content="Answer 5.") in history


@pytest.mark.asyncio
async def test_create_message_ignores_legacy_contentless_context_refs() -> None:
    user = CurrentUser(id=uuid4())
    session = FakeSession()
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
                retrieved_context=[
                    {
                        "chunkId": "legacy_chunk",
                        "sourceId": "doc_1",
                        "sourceTitle": "Biology Notes",
                    }
                ],
            ),
        ],
    )
    llm_service = FakeLLMService(
        LLMResult(
            content="A cell is a basic unit of life.",
            provider_response=ProviderResponse(content="A cell is a basic unit of life."),
        )
    )
    service = ChatService(
        session=session,
        current_user=user,
        llm_service=llm_service,
        repository=repository,
    )

    await service.create_message(conversation.id, "Tell me more.")

    assert llm_service.requests[0].history == [
        ChatMessage(role=ChatRole.USER, content="What is a cell?"),
    ]


@pytest.mark.asyncio
async def test_blocked_input_returns_blocked_assistant_message() -> None:
    user = CurrentUser(id=uuid4())
    session = FakeSession()
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
        session=session,
        current_user=user,
        llm_service=llm_service,
        repository=repository,
    )

    response = await service.create_conversation_message("unsafe")

    assert response.assistant_message.status == MessageStatus.BLOCKED
    assert response.assistant_message.content == "Input blocked."
    assert response.blocked_reason == "Input blocked."
    assert repository.messages[-1].blocked_reason == "Input blocked."
    assert session.commit_count == 2


@pytest.mark.asyncio
async def test_blocked_output_returns_blocked_assistant_message() -> None:
    user = CurrentUser(id=uuid4())
    session = FakeSession()
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
        session=session,
        current_user=user,
        llm_service=llm_service,
        repository=repository,
    )

    response = await service.create_conversation_message("safe input")

    assert response.assistant_message.status == MessageStatus.BLOCKED
    assert response.assistant_message.content == "Output blocked."
    assert response.blocked_reason == "Output blocked."
    assert session.commit_count == 2


@pytest.mark.asyncio
async def test_llm_exception_marks_assistant_failed_and_raises_api_error() -> None:
    user = CurrentUser(id=uuid4())
    session = FakeSession()
    repository = FakeChatRepository(user_id=user.id)
    service = ChatService(
        session=session,
        current_user=user,
        llm_service=FailingLLMService(),
        repository=repository,
    )

    with pytest.raises(ApiError) as exc_info:
        await service.create_conversation_message("Explain cells.")

    assert exc_info.value.code == "llm_unavailable"
    assert repository.messages[-1].status == MessageStatus.FAILED.value
    assert repository.messages[-1].error == {"type": "RuntimeError"}
    assert session.commit_count == 2


@pytest.mark.asyncio
async def test_message_sequence_conflict_rolls_back_and_skips_llm() -> None:
    user = CurrentUser(id=uuid4())
    session = FakeSession()
    llm_service = FakeLLMService(
        LLMResult(
            content="Cells are small units.",
            provider_response=ProviderResponse(content="Cells are small units."),
        )
    )
    service = ChatService(
        session=session,
        current_user=user,
        llm_service=llm_service,
        repository=ConflictingChatRepository(user_id=user.id),
    )

    with pytest.raises(ApiError) as exc_info:
        await service.create_conversation_message("Explain cells.")

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "message_sequence_conflict"
    assert session.rollback_count == 1
    assert llm_service.requests == []


class FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.rollback_count = 0

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1


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
                [item for item in self.messages if item.conversation_id == conversation.id]
            )
            + 1,
            role=role,
            status=status,
            content=content,
        )
        self.messages.append(message)
        return message


class ConflictingChatRepository(FakeChatRepository):
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
        raise IntegrityError(
            statement="INSERT INTO message",
            params={},
            orig=Exception("message sequence conflict"),
        )


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
    retrieved_context: list[dict] | None = None,
) -> Message:
    return Message(
        id=uuid4(),
        conversation_id=conversation.id,
        user_id=user_id,
        sequence=sequence,
        role=role.value,
        status=status.value,
        content=content,
        retrieved_context=retrieved_context or [],
        extra_metadata={},
        created_at=datetime.now(UTC),
    )
