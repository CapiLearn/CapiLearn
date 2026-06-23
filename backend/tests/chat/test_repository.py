from uuid import uuid4

import pytest

from backend.chat.models import LLMCostComponent
from backend.chat.repository import ChatRepository
from backend.llm.schemas import LLMCostComponent as LLMCostComponentRecord


@pytest.mark.asyncio
async def test_create_conversation_persists_explicit_metadata() -> None:
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
async def test_create_llm_cost_components_does_not_drop_invalid_missing_assistant_id() -> None:
    session = FakeSession()
    repository = ChatRepository()
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

    await repository.create_llm_cost_components(
        session,
        components=[invalid_component],
    )

    assert len(session.added) == 1
    assert session.added[0].assistant_message_id is None
    assert session.flushes == 1


class FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.flushes = 0

    def add(self, instance) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        self.flushes += 1
