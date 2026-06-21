from datetime import datetime
from uuid import uuid4

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.auth.models import UserAccount
from backend.chat.models import Conversation, Message
from backend.chat.schemas import MessageRole, MessageStatus


class SyncSession:
    def __init__(self, session: Session) -> None:
        self._session = session

    async def execute(self, statement):
        return self._session.execute(statement)

    async def scalar(self, statement):
        return self._session.scalar(statement)


def create_usage_tables(engine: Engine) -> None:
    UserAccount.__table__.create(engine)
    Conversation.__table__.create(engine)
    Message.__table__.create(engine)


def usage_user(
    clerk_id: str,
    first_name: str,
    last_name: str,
    role: str,
    *,
    deleted_at: datetime | None = None,
) -> UserAccount:
    return UserAccount(
        id=uuid4(),
        clerk_id=clerk_id,
        first_name=first_name,
        last_name=last_name,
        role=role,
        deleted_at=deleted_at,
    )


def usage_conversation(user: UserAccount) -> Conversation:
    return Conversation(
        id=uuid4(),
        user_id=user.id,
        model_profile_key="test-profile",
    )


def usage_message(
    *,
    conversation: Conversation,
    user: UserAccount,
    sequence: int,
    role: MessageRole,
    status: MessageStatus,
    created_at: datetime,
) -> Message:
    return Message(
        id=uuid4(),
        conversation_id=conversation.id,
        user_id=user.id,
        sequence=sequence,
        role=role.value,
        status=status.value,
        content="test",
        created_at=created_at,
    )
