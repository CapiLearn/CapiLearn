from datetime import UTC, datetime
from uuid import uuid4

import pytest

from backend.auth.schemas import CurrentUser
from backend.chat.models import Conversation
from backend.chat.schemas import ConversationStatus, ConversationUpdateRequest
from backend.chat.service import ChatService


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected_title"),
    [
        (ConversationUpdateRequest(title="New title"), "New title"),
        (ConversationUpdateRequest(), "Existing title"),
        (ConversationUpdateRequest(title=None), None),
    ],
)
async def test_update_conversation_title_semantics(
    payload: ConversationUpdateRequest,
    expected_title: str | None,
) -> None:
    user = CurrentUser(id=uuid4())
    conversation = Conversation(
        id=uuid4(),
        user_id=user.id,
        title="Existing title",
        status=ConversationStatus.ACTIVE.value,
        langgraph_thread_id="thread",
        model_profile_key="model",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repository = FakeUpdateRepository(conversation)
    service = ChatService(
        session=object(),
        current_user=user,
        llm_service=object(),
        repository=repository,
    )

    response = await service.update_conversation(conversation.id, payload)

    assert conversation.title == expected_title
    assert response.title == expected_title
    assert repository.saved


class FakeUpdateRepository:
    def __init__(self, conversation: Conversation) -> None:
        self.conversation = conversation
        self.saved = False

    async def get_conversation(self, session, *, conversation_id, user_id):
        if (
            conversation_id == self.conversation.id
            and user_id == self.conversation.user_id
        ):
            return self.conversation
        return None

    async def save(self, session) -> None:
        self.saved = True
