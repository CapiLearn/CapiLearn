import subprocess
import sys

from sqlalchemy import Uuid

from backend.chat.models import Conversation, Message


def test_conversation_user_id_references_user_account() -> None:
    assert _foreign_key_targets(Conversation.__table__.c.user_id) == {"user_account.id"}


def test_message_user_id_references_user_account() -> None:
    assert _foreign_key_targets(Message.__table__.c.user_id) == {"user_account.id"}


def test_user_id_columns_stay_uuid_typed_when_auth_models_are_not_imported() -> None:
    check = """
from sqlalchemy import Uuid
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateColumn

from backend.chat.models import Conversation, Message

assert isinstance(Conversation.__table__.c.user_id.type, Uuid)
assert isinstance(Message.__table__.c.user_id.type, Uuid)
conversation_user_id_ddl = str(
    CreateColumn(Conversation.__table__.c.user_id).compile(dialect=postgresql.dialect())
)
message_user_id_ddl = str(
    CreateColumn(Message.__table__.c.user_id).compile(dialect=postgresql.dialect())
)
assert conversation_user_id_ddl == "user_id UUID NOT NULL"
assert message_user_id_ddl == "user_id UUID NOT NULL"
"""

    subprocess.run(
        [sys.executable, "-c", check],
        check=True,
        capture_output=True,
        text=True,
    )


def test_user_id_columns_are_uuid_typed() -> None:
    assert isinstance(Conversation.__table__.c.user_id.type, Uuid)
    assert isinstance(Message.__table__.c.user_id.type, Uuid)


def _foreign_key_targets(column) -> set[str]:
    return {foreign_key.target_fullname for foreign_key in column.foreign_keys}
