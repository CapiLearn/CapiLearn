from uuid import uuid4

import pytest

from backend.chat.repository import ChatRepository


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


class FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.flushes = 0

    def add(self, instance) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        self.flushes += 1
