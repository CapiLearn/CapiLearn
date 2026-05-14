import pytest
from pydantic import ValidationError

from backend.chat.schemas import SendMessageRequest


def test_send_message_request_rejects_empty_content() -> None:
    with pytest.raises(ValidationError):
        SendMessageRequest(content="")


def test_send_message_request_rejects_oversized_content() -> None:
    with pytest.raises(ValidationError):
        SendMessageRequest(content="x" * 8001)


def test_send_message_request_accepts_valid_content() -> None:
    payload = SendMessageRequest(content="Explain photosynthesis.")

    assert payload.content == "Explain photosynthesis."
