import subprocess
import sys

from sqlalchemy import Uuid

from backend.chat.models import Conversation, LLMCostComponent, Message


def test_conversation_user_id_references_user_account() -> None:
    assert _foreign_key_targets(Conversation.__table__.c.user_id) == {"user_account.id"}


def test_message_user_id_references_user_account() -> None:
    assert _foreign_key_targets(Message.__table__.c.user_id) == {"user_account.id"}


def test_message_uses_minimal_history_context_column() -> None:
    assert "retrieved_context" not in Message.__table__.c
    assert "history_context" in Message.__table__.c


def test_chat_persistence_omits_redundant_metadata_columns() -> None:
    assert "metadata" not in Conversation.__table__.c
    assert "metadata" not in Message.__table__.c


def test_message_persistence_omits_redundant_provider_and_guardrail_columns() -> None:
    removed_columns = {
        "provider_message_id",
        "provider_response",
        "finish_reason",
        "input_guardrail_result",
        "output_guardrail_result",
    }

    assert removed_columns.isdisjoint(Message.__table__.c.keys())


def test_llm_cost_component_user_id_references_user_account() -> None:
    assert _foreign_key_targets(LLMCostComponent.__table__.c.user_id) == {"user_account.id"}


def test_user_id_columns_stay_uuid_typed_when_auth_models_are_not_imported() -> None:
    check = """
from sqlalchemy import Uuid
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateColumn

from backend.chat.models import Conversation, LLMCostComponent, Message

assert isinstance(Conversation.__table__.c.user_id.type, Uuid)
assert isinstance(Message.__table__.c.user_id.type, Uuid)
assert isinstance(LLMCostComponent.__table__.c.user_id.type, Uuid)
conversation_user_id_ddl = str(
    CreateColumn(Conversation.__table__.c.user_id).compile(dialect=postgresql.dialect())
)
message_user_id_ddl = str(
    CreateColumn(Message.__table__.c.user_id).compile(dialect=postgresql.dialect())
)
cost_component_user_id_ddl = str(
    CreateColumn(LLMCostComponent.__table__.c.user_id).compile(
        dialect=postgresql.dialect()
    )
)
assert conversation_user_id_ddl == "user_id UUID NOT NULL"
assert message_user_id_ddl == "user_id UUID NOT NULL"
assert cost_component_user_id_ddl == "user_id UUID NOT NULL"
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
    assert isinstance(LLMCostComponent.__table__.c.user_id.type, Uuid)


def _foreign_key_targets(column) -> set[str]:
    return {foreign_key.target_fullname for foreign_key in column.foreign_keys}
