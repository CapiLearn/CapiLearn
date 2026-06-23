import logging
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from backend.auth.schemas import CurrentUser, UserRole
from backend.chat.models import Conversation, Message
from backend.chat.schemas import (
    ConversationStatus,
    MessageRole,
    MessageStatus,
)
from backend.chat.service import ChatService
from backend.core.exceptions import ApiError
from backend.core.observability import (
    BestEffortLLMTraceSink,
    LLMTraceSink,
    NoopLLMTraceSink,
)
from backend.llm.schemas import (
    ChatMessage,
    ChatRole,
    GuardrailResult,
    LLMCostComponent,
    LLMResult,
    ProviderResponse,
)
from backend.llm.service import LLMServiceError
from backend.rag.schemas import RetrievalResult, RetrievedChunk


def _current_user() -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        clerk_id=f"user_{uuid4().hex}",
        display_name="Test User",
        role=UserRole.STUDENT,
    )


@pytest.mark.asyncio
async def test_create_conversation_message_completes_assistant_message(caplog) -> None:
    caplog.set_level(logging.INFO, logger="backend.chat.service")
    user = _current_user()
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
                    distance=0.42,
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
        user_id=user.id,
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
            "distance": 0.42,
        }
    ]
    request_id = repository.messages[0].extra_metadata["requestId"]
    assert request_id
    assert repository.messages[-1].extra_metadata["requestId"] == request_id
    assert repository.messages[-1].latency_ms is not None
    assert repository.messages[-1].latency_ms >= 0
    assert repository.cost_components == []
    assert repository.messages[-1].retrieved_context in (None, [])
    assert repository.messages[-1].citations in (None, [])
    assert _events(caplog.records, "chat.turn.started")
    completed_events = _events(caplog.records, "chat.turn.completed")
    assert completed_events
    assert completed_events[-1].assistant_message_id == str(repository.messages[-1].id)


@pytest.mark.asyncio
async def test_create_message_uses_completed_history() -> None:
    user = _current_user()
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
        user_id=user.id,
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
@pytest.mark.parametrize(
    ("role", "sequence"),
    [
        (MessageRole.USER, 1),
        (MessageRole.ASSISTANT, 2),
    ],
)
async def test_create_message_rejects_completed_history_missing_content(
    role: MessageRole,
    sequence: int,
) -> None:
    service, session, _repository, llm_service, conversation = _service_with_existing_message(
        sequence=sequence,
        role=role,
        status=MessageStatus.COMPLETED,
        content=None,
        llm_result=LLMResult(
            content="Cells contain organelles.",
            provider_response=ProviderResponse(content="Cells contain organelles."),
        ),
    )

    with pytest.raises(ValueError, match="missing required content"):
        await service.create_message(conversation.id, "Tell me more.")

    assert llm_service.requests == []
    assert session.commit_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "status"),
    [
        (MessageRole.USER, MessageStatus.COMPLETED),
        (MessageRole.ASSISTANT, MessageStatus.COMPLETED),
        (MessageRole.ASSISTANT, MessageStatus.BLOCKED),
    ],
)
async def test_list_messages_rejects_required_response_content_missing(
    role: MessageRole,
    status: MessageStatus,
) -> None:
    service, _session, _repository, _llm_service, conversation = _service_with_existing_message(
        role=role,
        status=status,
        content=None,
    )

    with pytest.raises(ValueError, match="missing required content"):
        await service.list_messages(conversation.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [MessageStatus.PENDING, MessageStatus.FAILED])
async def test_list_messages_allows_empty_unfinished_assistant_content(
    status: MessageStatus,
) -> None:
    service, _session, _repository, _llm_service, conversation = _service_with_existing_message(
        role=MessageRole.ASSISTANT,
        status=status,
        content=None,
    )

    response = await service.list_messages(conversation.id)

    assert response.messages[0].content == ""
    assert response.messages[0].status == status


@pytest.mark.asyncio
async def test_create_conversation_message_warns_when_provider_metadata_missing(
    caplog,
) -> None:
    caplog.set_level(logging.WARNING, logger="backend.chat.service")
    service, _session, repository = _new_conversation_service(
        LLMResult(content="ok", provider_response=None)
    )

    response = await service.create_conversation_message("Explain cells.")

    assert response.assistant_message.status == MessageStatus.COMPLETED
    assert response.assistant_message.content == "ok"
    assert response.finish_reason is None
    assert repository.messages[-1].finish_reason is None
    assert repository.messages[-1].provider_response is None
    warning_events = _events(caplog.records, "chat.turn.provider_response_missing")
    assert len(warning_events) == 1
    assert warning_events[0].status == MessageStatus.COMPLETED.value
    assert warning_events[0].conversation_id == str(response.conversation.id)
    assert warning_events[0].assistant_message_id == str(repository.messages[-1].id)


@pytest.mark.asyncio
async def test_blocked_message_warns_when_provider_metadata_missing(caplog) -> None:
    caplog.set_level(logging.WARNING, logger="backend.chat.service")
    service, _session, _repository = _new_conversation_service(
        LLMResult(
            content="Input blocked.",
            input_guardrail_result=GuardrailResult(
                blocked=True,
                reason="Input blocked.",
                rail="input",
            ),
            provider_response=None,
        )
    )

    response = await service.create_conversation_message("unsafe")

    assert response.assistant_message.status == MessageStatus.BLOCKED
    assert response.blocked_reason == "Input blocked."
    warning_events = _events(caplog.records, "chat.turn.provider_response_missing")
    assert len(warning_events) == 1
    assert warning_events[0].status == MessageStatus.BLOCKED.value


@pytest.mark.asyncio
async def test_create_conversation_message_persists_llm_cost_components() -> None:
    user = _current_user()
    session = FakeSession()
    repository = FakeChatRepository(user_id=user.id)
    llm_service = FakeLLMService(
        LLMResult(
            content="Cells are small units.",
            provider_response=ProviderResponse(content="Cells are small units."),
            cost_components=[
                LLMCostComponent(
                    user_id=user.id,
                    conversation_id=uuid4(),
                    user_message_id=uuid4(),
                    assistant_message_id=uuid4(),
                    component_order=1,
                    component_type="main_generation",
                    status="completed",
                    estimated_cost_usd="0.001000000000",
                )
            ],
        )
    )
    service = ChatService(
        session=session,
        user_id=user.id,
        llm_service=llm_service,
        repository=repository,
    )

    await service.create_conversation_message("Explain cells.")

    assert repository.cost_components == llm_service.result.cost_components
    assert repository.cost_components[0].estimated_cost_usd == Decimal("0.001000000000")


@pytest.mark.asyncio
async def test_create_message_adds_stored_context_to_recent_user_history() -> None:
    user = _current_user()
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
                            "distance": 0.12,
                            "similarity": 0.88,
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
        user_id=user.id,
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
@pytest.mark.parametrize(
    "retrieved_context",
    [
        pytest.param(
            [{"content": "Stored note", "metadata": "bad"}],
            id="current-metadata-not-mapping",
        ),
        pytest.param(
            [{"metadata": {"source": "Biology Notes"}}],
            id="missing-content",
        ),
        pytest.param([42], id="scalar-item"),
    ],
)
async def test_create_message_rejects_malformed_retrieved_context(
    retrieved_context,
) -> None:
    service, session, _repository, llm_service, conversation = _service_with_existing_message(
        role=MessageRole.USER,
        status=MessageStatus.COMPLETED,
        content="What is a cell?",
        retrieved_context=retrieved_context,
        llm_result=LLMResult(
            content="A cell is a basic unit of life.",
            provider_response=ProviderResponse(content="A cell is a basic unit of life."),
        ),
    )

    with pytest.raises(ValueError, match="retrieved context is malformed"):
        await service.create_message(conversation.id, "Tell me more.")

    assert llm_service.requests == []
    assert session.commit_count == 0


@pytest.mark.asyncio
async def test_blocked_input_returns_blocked_assistant_message(caplog) -> None:
    caplog.set_level(logging.INFO, logger="backend.chat.service")
    user = _current_user()
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
        user_id=user.id,
        llm_service=llm_service,
        repository=repository,
    )

    response = await service.create_conversation_message("unsafe")

    assert response.assistant_message.status == MessageStatus.BLOCKED
    assert response.assistant_message.content == "Input blocked."
    assert response.blocked_reason == "Input blocked."
    assert repository.messages[-1].blocked_reason == "Input blocked."
    assert repository.messages[-1].latency_ms is not None
    assert _events(caplog.records, "chat.turn.blocked")
    assert session.commit_count == 2


@pytest.mark.asyncio
async def test_blocked_output_returns_blocked_assistant_message() -> None:
    user = _current_user()
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
        user_id=user.id,
        llm_service=llm_service,
        repository=repository,
    )

    response = await service.create_conversation_message("safe input")

    assert response.assistant_message.status == MessageStatus.BLOCKED
    assert response.assistant_message.content == "Output blocked."
    assert response.blocked_reason == "Output blocked."
    assert session.commit_count == 2


@pytest.mark.asyncio
async def test_llm_exception_marks_assistant_failed_and_raises_api_error(caplog) -> None:
    caplog.set_level(logging.INFO, logger="backend.chat.service")
    user = _current_user()
    session = FakeSession()
    repository = FakeChatRepository(user_id=user.id)
    service = ChatService(
        session=session,
        user_id=user.id,
        llm_service=FailingLLMService(),
        repository=repository,
    )

    with pytest.raises(ApiError) as exc_info:
        await service.create_conversation_message("Explain cells.")

    assert exc_info.value.code == "llm_unavailable"
    assert repository.messages[-1].status == MessageStatus.FAILED.value
    assert repository.messages[-1].error == {"type": "RuntimeError"}
    assert repository.messages[-1].latency_ms is not None
    failed_events = _events(caplog.records, "chat.turn.failed")
    assert failed_events
    assert failed_events[-1].error_type == "RuntimeError"
    assert session.commit_count == 2


@pytest.mark.asyncio
async def test_llm_service_error_persists_failed_cost_components() -> None:
    user = _current_user()
    session = FakeSession()
    repository = FakeChatRepository(user_id=user.id)
    llm_service = FailingCostedLLMService()
    service = ChatService(
        session=session,
        user_id=user.id,
        llm_service=llm_service,
        repository=repository,
    )

    with pytest.raises(ApiError) as exc_info:
        await service.create_conversation_message("Explain cells.")

    assert exc_info.value.code == "llm_unavailable"
    assert repository.messages[-1].status == MessageStatus.FAILED.value
    assert repository.messages[-1].error == {"type": "RuntimeError"}
    assert repository.cost_components == llm_service.cost_components
    assert repository.cost_components[0].assistant_message_id == repository.messages[-1].id
    assert session.commit_count == 2


@pytest.mark.asyncio
async def test_default_trace_sink_is_explicit_noop() -> None:
    user = _current_user()
    service = ChatService(
        session=FakeSession(),
        user_id=user.id,
        llm_service=FakeLLMService(LLMResult(content="ok")),
        repository=FakeChatRepository(user_id=user.id),
    )

    assert isinstance(service._trace_sink, NoopLLMTraceSink)


@pytest.mark.asyncio
async def test_incomplete_trace_sink_cannot_be_constructed() -> None:
    with pytest.raises(TypeError):
        IncompleteTraceSink()


@pytest.mark.asyncio
async def test_trace_sink_failure_does_not_block_completed_message(caplog) -> None:
    caplog.set_level(logging.WARNING, logger="backend.core.observability.tracing")
    user = _current_user()
    session = FakeSession()
    repository = FakeChatRepository(user_id=user.id)
    service = ChatService(
        session=session,
        user_id=user.id,
        llm_service=FakeLLMService(
            LLMResult(
                content="Cells are small units.",
                provider_response=ProviderResponse(content="Cells are small units."),
            )
        ),
        repository=repository,
        trace_sink=BestEffortLLMTraceSink(FailingTraceSink()),
    )

    response = await service.create_conversation_message("Explain cells.")

    assert response.assistant_message.status == MessageStatus.COMPLETED
    assert repository.messages[-1].status == MessageStatus.COMPLETED.value
    assert repository.messages[-1].content == "Cells are small units."
    assert session.commit_count == 2
    assert _events(caplog.records, "trace_sink.failed")


@pytest.mark.asyncio
async def test_trace_sink_failure_does_not_block_blocked_message() -> None:
    user = _current_user()
    session = FakeSession()
    repository = FakeChatRepository(user_id=user.id)
    service = ChatService(
        session=session,
        user_id=user.id,
        llm_service=FakeLLMService(
            LLMResult(
                content="Input blocked.",
                input_guardrail_result=GuardrailResult(
                    blocked=True,
                    reason="Input blocked.",
                    rail="input",
                ),
            )
        ),
        repository=repository,
        trace_sink=BestEffortLLMTraceSink(FailingTraceSink()),
    )

    response = await service.create_conversation_message("unsafe")

    assert response.assistant_message.status == MessageStatus.BLOCKED
    assert repository.messages[-1].status == MessageStatus.BLOCKED.value
    assert repository.messages[-1].blocked_reason == "Input blocked."
    assert session.commit_count == 2


@pytest.mark.asyncio
async def test_trace_sink_failure_preserves_llm_unavailable_error() -> None:
    user = _current_user()
    session = FakeSession()
    repository = FakeChatRepository(user_id=user.id)
    service = ChatService(
        session=session,
        user_id=user.id,
        llm_service=FailingLLMService(),
        repository=repository,
        trace_sink=BestEffortLLMTraceSink(FailingTraceSink()),
    )

    with pytest.raises(ApiError) as exc_info:
        await service.create_conversation_message("Explain cells.")

    assert exc_info.value.code == "llm_unavailable"
    assert repository.messages[-1].status == MessageStatus.FAILED.value
    assert repository.messages[-1].error == {"type": "RuntimeError"}
    assert session.commit_count == 2


@pytest.mark.asyncio
async def test_message_sequence_conflict_rolls_back_and_skips_llm() -> None:
    user = _current_user()
    session = FakeSession()
    llm_service = FakeLLMService(
        LLMResult(
            content="Cells are small units.",
            provider_response=ProviderResponse(content="Cells are small units."),
        )
    )
    service = ChatService(
        session=session,
        user_id=user.id,
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
        self.cost_components = []

    async def create_conversation(
        self,
        session,
        *,
        user_id,
        title,
        model_profile_key,
        model_profile_version,
        guardrails_config_id,
        rag_index_version,
    ):
        conversation = _conversation(
            user_id=user_id,
            title=title,
            model_profile_key=model_profile_key,
            model_profile_version=model_profile_version,
            guardrails_config_id=guardrails_config_id,
            rag_index_version=rag_index_version,
        )
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

    async def create_llm_cost_components(self, session, *, components):
        self.cost_components.extend(components)


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


class FailingCostedLLMService:
    def __init__(self) -> None:
        self.cost_components = []

    async def complete(self, request):
        self.cost_components = [
            LLMCostComponent(
                user_id=request.user_id,
                conversation_id=request.conversation_id,
                user_message_id=request.user_message_id,
                assistant_message_id=request.assistant_message_id,
                component_order=1,
                component_type="main_generation",
                status="failed",
                error_type="RuntimeError",
            )
        ]
        raise LLMServiceError(
            RuntimeError("provider unavailable"),
            cost_components=self.cost_components,
        )


class IncompleteTraceSink(LLMTraceSink):
    pass


class FailingTraceSink(NoopLLMTraceSink):
    async def record(self, operation, metadata):
        raise RuntimeError("trace sink unavailable")


def _new_conversation_service(llm_result: LLMResult):
    user = _current_user()
    session = FakeSession()
    repository = FakeChatRepository(user_id=user.id)
    service = ChatService(
        session=session,
        user_id=user.id,
        llm_service=FakeLLMService(llm_result),
        repository=repository,
    )
    return service, session, repository


def _service_with_existing_message(
    *,
    role: MessageRole,
    status: MessageStatus,
    content: str | None,
    sequence: int = 1,
    retrieved_context=None,
    llm_result: LLMResult | None = None,
):
    user = _current_user()
    session = FakeSession()
    conversation = _conversation(user_id=user.id)
    repository = FakeChatRepository(
        user_id=user.id,
        conversations=[conversation],
        messages=[
            _message(
                conversation=conversation,
                user_id=user.id,
                sequence=sequence,
                role=role,
                status=status,
                content=content,
                retrieved_context=retrieved_context,
            ),
        ],
    )
    llm_service = FakeLLMService(llm_result or LLMResult(content="unused"))
    service = ChatService(
        session=session,
        user_id=user.id,
        llm_service=llm_service,
        repository=repository,
    )
    return service, session, repository, llm_service, conversation


def _events(records, event: str):
    return [record for record in records if getattr(record, "event", None) == event]


def _conversation(
    *,
    user_id,
    title: str | None = "Existing title",
    model_profile_key: str = "model",
    model_profile_version: str | None = None,
    guardrails_config_id: str | None = None,
    rag_index_version: str | None = None,
) -> Conversation:
    now = datetime.now(UTC)
    return Conversation(
        id=uuid4(),
        user_id=user_id,
        title=title,
        status=ConversationStatus.ACTIVE.value,
        model_profile_key=model_profile_key,
        model_profile_version=model_profile_version,
        guardrails_config_id=guardrails_config_id,
        rag_index_version=rag_index_version,
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
    content: str | None,
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
