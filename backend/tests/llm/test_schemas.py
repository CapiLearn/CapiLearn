from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.llm.schemas import LLMCostComponent, LLMRequest


def test_llm_request_requires_assistant_message_id() -> None:
    with pytest.raises(ValidationError):
        LLMRequest(
            user_id=uuid4(),
            conversation_id=uuid4(),
            user_message_id=uuid4(),
            content="Explain cells.",
        )


def test_llm_request_rejects_null_assistant_message_id() -> None:
    with pytest.raises(ValidationError):
        LLMRequest(
            user_id=uuid4(),
            conversation_id=uuid4(),
            user_message_id=uuid4(),
            assistant_message_id=None,
            content="Explain cells.",
        )


def test_llm_cost_component_requires_assistant_message_id() -> None:
    with pytest.raises(ValidationError):
        LLMCostComponent(
            user_id=uuid4(),
            conversation_id=uuid4(),
            user_message_id=uuid4(),
            component_order=1,
            component_type="main_generation",
            status="completed",
        )


def test_llm_cost_component_rejects_null_assistant_message_id() -> None:
    with pytest.raises(ValidationError):
        LLMCostComponent(
            user_id=uuid4(),
            conversation_id=uuid4(),
            user_message_id=uuid4(),
            assistant_message_id=None,
            component_order=1,
            component_type="main_generation",
            status="completed",
        )
