from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from backend.chat.models import Conversation, LLMCostComponent
from backend.chat.repository import ChatRepository, MessageSequenceConflictError
from backend.chat.schemas import MessageRole, MessageStatus
from backend.llm.schemas import LLMCostComponent as LLMCostComponentRecord


@pytest.mark.asyncio
async def test_create_conversation_persists_explicit_configuration_fields() -> None:
    session = FakeSession()
    repository = ChatRepository()

    conversation = await repository.create_conversation(
        session,
        user_id=uuid4(),
        title="Explain cells.",
        model_profile_key="default_tutor",
        model_profile_version="2026-05-10",
        guardrails_config_id="default",
        rag_index_version="fso-2026-06",
    )

    assert conversation.model_profile_key == "default_tutor"
    assert conversation.model_profile_version == "2026-05-10"
    assert conversation.guardrails_config_id == "default"
    assert conversation.rag_index_version == "fso-2026-06"
    assert session.added == [conversation]
    assert session.flushes == 1


@pytest.mark.asyncio
async def test_create_llm_cost_components_persists_assistant_message_id() -> None:
    session = FakeSession()
    repository = ChatRepository()
    assistant_message_id = uuid4()

    await repository.create_llm_cost_components(
        session,
        components=[
            LLMCostComponentRecord(
                user_id=uuid4(),
                conversation_id=uuid4(),
                user_message_id=uuid4(),
                assistant_message_id=assistant_message_id,
                component_order=1,
                component_type="main_generation",
                status="completed",
            )
        ],
    )

    assert len(session.added) == 1
    stored = session.added[0]
    assert isinstance(stored, LLMCostComponent)
    assert stored.assistant_message_id == assistant_message_id
    assert session.flushes == 1


@pytest.mark.asyncio
async def test_create_turn_messages_persists_adjacent_user_and_assistant_messages() -> None:
    user_id = uuid4()
    session = FakeSession(scalar_result=4)
    repository = ChatRepository()
    conversation = _conversation(user_id=user_id)

    user_message, assistant_message = await repository.create_turn_messages(
        session,
        conversation=conversation,
        user_id=user_id,
        content="Explain cells.",
    )

    assert session.scalar_count == 1
    assert session.flushes == 1
    assert session.added == [user_message, assistant_message]
    assert user_message.conversation_id == conversation.id
    assert user_message.user_id == user_id
    assert user_message.sequence == 5
    assert user_message.role == MessageRole.USER.value
    assert user_message.status == MessageStatus.COMPLETED.value
    assert user_message.content == "Explain cells."
    assert assistant_message.conversation_id == conversation.id
    assert assistant_message.user_id == user_id
    assert assistant_message.sequence == 6
    assert assistant_message.role == MessageRole.ASSISTANT.value
    assert assistant_message.status == MessageStatus.PENDING.value
    assert assistant_message.content == ""


@pytest.mark.asyncio
async def test_create_turn_messages_maps_sequence_conflict_to_domain_error() -> None:
    user_id = uuid4()
    session = FakeSession(
        flush_error=_integrity_error("message_conversation_sequence_key"),
    )
    repository = ChatRepository()

    with pytest.raises(MessageSequenceConflictError):
        await repository.create_turn_messages(
            session,
            conversation=_conversation(user_id=user_id),
            user_id=user_id,
            content="Explain cells.",
        )

    assert session.scalar_count == 1
    assert session.flushes == 1


@pytest.mark.asyncio
async def test_create_turn_messages_reraises_unrelated_integrity_error() -> None:
    user_id = uuid4()
    integrity_error = _integrity_error("message_user_id_fkey")
    session = FakeSession(flush_error=integrity_error)
    repository = ChatRepository()

    with pytest.raises(IntegrityError) as exc_info:
        await repository.create_turn_messages(
            session,
            conversation=_conversation(user_id=user_id),
            user_id=user_id,
            content="Explain cells.",
        )

    assert exc_info.value is integrity_error
    assert session.scalar_count == 1
    assert session.flushes == 1


@pytest.mark.asyncio
async def test_create_llm_cost_components_rejects_missing_assistant_id() -> None:
    session = FakeSession()
    repository = ChatRepository()
    valid_component = LLMCostComponentRecord(
        user_id=uuid4(),
        conversation_id=uuid4(),
        user_message_id=uuid4(),
        assistant_message_id=uuid4(),
        component_order=1,
        component_type="main_generation",
        status="completed",
    )
    invalid_component = LLMCostComponentRecord.model_construct(
        user_id=uuid4(),
        conversation_id=uuid4(),
        user_message_id=uuid4(),
        assistant_message_id=None,
        component_order=1,
        component_type="main_generation",
        attempt_index=1,
        provider=None,
        configured_model=None,
        response_model=None,
        finish_reason=None,
        status="completed",
        prompt_tokens=None,
        completion_tokens=None,
        total_tokens=None,
        estimated_cost_usd=None,
        latency_ms=None,
        error_type=None,
        metadata={},
    )

    with pytest.raises(ValueError, match="requires assistant_message_id"):
        await repository.create_llm_cost_components(
            session,
            components=[valid_component, invalid_component],
        )

    assert session.added == []
    assert session.flushes == 0


class FakeSession:
    def __init__(
        self,
        *,
        scalar_result: int | None = None,
        flush_error: IntegrityError | None = None,
    ) -> None:
        self.added = []
        self.flushes = 0
        self.scalar_count = 0
        self.scalar_result = scalar_result
        self.flush_error = flush_error

    def add(self, instance) -> None:
        self.added.append(instance)

    async def scalar(self, statement):
        self.scalar_count += 1
        return self.scalar_result

    async def flush(self) -> None:
        self.flushes += 1
        if self.flush_error is not None:
            raise self.flush_error


def _conversation(*, user_id) -> Conversation:
    return Conversation(
        id=uuid4(),
        user_id=user_id,
        title="Explain cells.",
        model_profile_key="default_tutor",
    )


def _integrity_error(constraint_name: str) -> IntegrityError:
    return IntegrityError(
        statement="INSERT INTO message",
        params={},
        orig=FakeAsyncpgIntegrityWrapper(FakeAsyncpgUniqueViolation(constraint_name)),
    )


class FakeAsyncpgIntegrityWrapper(Exception):
    def __init__(self, cause: BaseException) -> None:
        super().__init__(str(cause))
        self.__cause__ = cause


class FakeAsyncpgUniqueViolation(Exception):
    def __init__(self, constraint_name: str) -> None:
        super().__init__(constraint_name)
        self.constraint_name = constraint_name
