import json
import logging
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from backend.chat.schemas import MessageRole, MessageStatus
from backend.chat.service import ChatService
from backend.core.exceptions import ApiError
from backend.core.observability import (
    BestEffortLLMTraceSink,
    NoopLLMTraceSink,
)
from backend.llm.schemas import (
    ChatMessage,
    ChatRole,
    GuardrailResult,
    LLMResult,
    ProviderResponse,
)
from backend.rag.schemas import RetrievalResult, RetrievedChunk
from backend.tests.chat.service_helpers import (
    ConflictingChatRepository,
    CostedLLMService,
    FailingCostedLLMService,
    FailingLLMService,
    FailingTraceSink,
    FakeChatRepository,
    FakeLLMService,
    FakeSession,
    IncompleteTraceSink,
    _conversation,
    _current_user,
    _events,
    _message,
    _new_conversation_service,
    _service_with_existing_message,
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
                    metadata={
                        "source_id": "doc_1",
                        "title": "Biology Notes",
                        "section_heading": "Cells",
                    },
                    distance=0.42,
                )
            ],
            provider_response=ProviderResponse(
                content="Cells are small units.",
                finish_reason="stop",
                prompt_tokens=4,
                completion_tokens=5,
                total_tokens=9,
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
    assert response.assistant_message.citations == []
    assert response.finish_reason == "stop"
    assert response.blocked_reason is None
    assert llm_service.requests[0].history == []
    assert session.commit_count == 2
    assert repository.messages[0].history_context == [
        {
            "content": "Cell note",
            "heading": "Cells",
        }
    ]
    assert "metadata" not in repository.messages[0].history_context[0]
    assert "distance" not in repository.messages[0].history_context[0]
    assert repository.messages[-1].latency_ms is not None
    assert repository.messages[-1].latency_ms >= 0
    assert not hasattr(repository.messages[-1], "content" + "_parts")
    assert repository.cost_components == []
    assert repository.messages[-1].history_context in (None, [])
    assert repository.messages[-1].citations == []
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
                content="A cell is a basic unit of life. ",
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
    assert llm_service.requests[0].history[0].role == ChatRole.USER
    assert json.loads(llm_service.requests[0].history[0].content) == {
        "studentMessage": "What is a cell?",
        "previousRetrievedContext": [],
    }
    assert llm_service.requests[0].history[1] == ChatMessage(
        role=ChatRole.ASSISTANT,
        content="A cell is a basic unit of life. ",
    )


@pytest.mark.asyncio
async def test_create_message_rehydrates_assistant_cited_content_in_history() -> None:
    user = _current_user()
    session = FakeSession()
    conversation = _conversation(user_id=user.id)
    assistant_message = _message(
        conversation=conversation,
        user_id=user.id,
        sequence=2,
        role=MessageRole.ASSISTANT,
        status=MessageStatus.COMPLETED,
        content="State belongs to a component. [1]",
    )
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
                content="What owns state?",
            ),
            assistant_message,
        ],
    )
    llm_service = FakeLLMService(
        LLMResult(
            content="Components own local state.",
            provider_response=ProviderResponse(content="Components own local state."),
        )
    )
    service = ChatService(
        session=session,
        user_id=user.id,
        llm_service=llm_service,
        repository=repository,
    )

    await service.create_message(conversation.id, "Tell me more.")

    assert llm_service.requests[0].history[1] == ChatMessage(
        role=ChatRole.ASSISTANT,
        content="State belongs to a component. [1]",
    )
    assert assistant_message.content == "State belongs to a component. [1]"


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
async def test_list_messages_returns_assistant_cited_content() -> None:
    service, _session, repository, _llm_service, conversation = _service_with_existing_message(
        role=MessageRole.ASSISTANT,
        status=MessageStatus.COMPLETED,
        content="State belongs to a component. [1]",
    )

    response = await service.list_messages(conversation.id)

    assert response.messages[0].content == "State belongs to a component. [1]"
    assert repository.messages[0].content == "State belongs to a component. [1]"


@pytest.mark.asyncio
async def test_list_messages_returns_user_text_verbatim() -> None:
    service, _session, _repository, _llm_service, conversation = _service_with_existing_message(
        role=MessageRole.USER,
        status=MessageStatus.COMPLETED,
        content="Please explain this phrase literally: not a special token.",
    )

    response = await service.list_messages(conversation.id)

    assert response.messages[0].content == (
        "Please explain this phrase literally: not a special token."
    )


@pytest.mark.asyncio
async def test_create_conversation_message_warns_when_provider_response_missing(
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
    warning_events = _events(caplog.records, "chat.turn.provider_response_missing")
    assert len(warning_events) == 1
    assert warning_events[0].status == MessageStatus.COMPLETED.value
    assert warning_events[0].conversation_id == str(response.conversation.id)
    assert warning_events[0].assistant_message_id == str(repository.messages[-1].id)


@pytest.mark.asyncio
async def test_blocked_message_warns_when_provider_response_missing(caplog) -> None:
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
    llm_service = CostedLLMService()
    service = ChatService(
        session=session,
        user_id=user.id,
        llm_service=llm_service,
        repository=repository,
    )

    await service.create_conversation_message("Explain cells.")

    assert repository.cost_components == llm_service.result.cost_components
    assert repository.cost_components[0].assistant_message_id == repository.messages[-1].id
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
                history_context=[
                    {
                        "heading": f"Biology Notes {index}",
                        "content": f"Stored note for chunk_{index}",
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
    user_payloads = [json.loads(message.content) for message in user_history]
    assert [payload["studentMessage"] for payload in user_payloads[:2]] == [
        "Question 1?",
        "Question 2?",
    ]
    assert user_payloads[0]["previousRetrievedContext"] == []
    assert user_payloads[1]["previousRetrievedContext"] == []
    recent_payloads = user_payloads[2:5]
    assert [payload["previousRetrievedContext"][0]["content"] for payload in recent_payloads] == [
        "Stored note for chunk_3",
        "Stored note for chunk_4",
        "Stored note for chunk_5",
    ]
    assert [payload["previousRetrievedContext"][0]["heading"] for payload in recent_payloads] == [
        "Biology Notes 3",
        "Biology Notes 4",
        "Biology Notes 5",
    ]
    assert [payload["studentMessage"] for payload in recent_payloads] == [
        "Question 3?",
        "Question 4?",
        "Question 5?",
    ]
    assert "citationId" not in recent_payloads[0]["previousRetrievedContext"][0]
    assert ChatMessage(role=ChatRole.ASSISTANT, content="Answer 5.") in history


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "history_context",
    [
        pytest.param(
            [{"content": "Stored note", "metadata": {"source": "Biology Notes"}}],
            id="extra-metadata",
        ),
        pytest.param(
            [{"heading": "Biology Notes"}],
            id="missing-content",
        ),
        pytest.param([42], id="scalar-item"),
    ],
)
async def test_create_message_rejects_malformed_history_context(
    history_context,
) -> None:
    service, session, _repository, llm_service, conversation = _service_with_existing_message(
        role=MessageRole.USER,
        status=MessageStatus.COMPLETED,
        content="What is a cell?",
        history_context=history_context,
        llm_result=LLMResult(
            content="A cell is a basic unit of life.",
            provider_response=ProviderResponse(content="A cell is a basic unit of life."),
        ),
    )

    with pytest.raises(ValueError, match="history context is malformed"):
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
    assert response.assistant_message.citations == []
    assert response.blocked_reason == "Input blocked."
    assert repository.messages[-1].blocked_reason == "Input blocked."
    assert not hasattr(repository.messages[-1], "content" + "_parts")
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
    assert response.assistant_message.citations == []
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
    assert not hasattr(repository.messages[-1], "content" + "_parts")
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
    assert not hasattr(repository.messages[-1], "content" + "_parts")
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


@pytest.mark.asyncio
async def test_unrelated_message_integrity_error_rolls_back_and_reraises() -> None:
    user = _current_user()
    session = FakeSession()
    llm_service = FakeLLMService(
        LLMResult(
            content="Cells are small units.",
            provider_response=ProviderResponse(content="Cells are small units."),
        )
    )
    integrity_error = IntegrityError(
        statement="INSERT INTO message",
        params={},
        orig=Exception("message user id conflict"),
    )
    service = ChatService(
        session=session,
        user_id=user.id,
        llm_service=llm_service,
        repository=ConflictingChatRepository(
            user_id=user.id,
            exc=integrity_error,
        ),
    )

    with pytest.raises(IntegrityError):
        await service.create_conversation_message("Explain cells.")

    assert session.rollback_count == 1
    assert llm_service.requests == []
