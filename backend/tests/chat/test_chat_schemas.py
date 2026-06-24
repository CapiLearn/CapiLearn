from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.chat.schemas import (
    MessageResponse,
    MessageRole,
    MessageStatus,
    SendMessageRequest,
    StoredRagHistoryContext,
)
from backend.core.citations import CitationRecord


def test_send_message_request_rejects_empty_content() -> None:
    with pytest.raises(ValidationError):
        SendMessageRequest(content="")


def test_send_message_request_rejects_oversized_content() -> None:
    with pytest.raises(ValidationError):
        SendMessageRequest(content="x" * 8001)


def test_send_message_request_accepts_valid_content() -> None:
    payload = SendMessageRequest(content="Explain photosynthesis.")

    assert payload.content == "Explain photosynthesis."


def test_stored_rag_history_context_serializes_minimal_shape() -> None:
    payload = StoredRagHistoryContext(
        heading="State",
        content="State belongs to a component.",
    )

    assert payload.model_dump(mode="json", by_alias=True) == {
        "heading": "State",
        "content": "State belongs to a component.",
    }


def test_stored_rag_history_context_forbids_extra_metadata() -> None:
    with pytest.raises(ValidationError):
        StoredRagHistoryContext.model_validate(
            {
                "heading": "State",
                "content": "State belongs to a component.",
                "metadata": {"source": "state.md"},
            }
        )


def test_message_response_rejects_removed_structured_field() -> None:
    removed_field = "content" + "Parts"

    with pytest.raises(ValidationError):
        MessageResponse.model_validate(
            {
                "id": uuid4(),
                "conversationId": uuid4(),
                "role": MessageRole.ASSISTANT,
                "content": "State is local. [1]",
                removed_field: [
                    {"type": "text", "text": "State is local. "},
                    {"type": "citation", "citationId": "1"},
                ],
                "status": MessageStatus.COMPLETED,
                "createdAt": datetime.now(UTC),
                "citations": [],
            }
        )


def test_message_response_requires_explicit_citations() -> None:
    with pytest.raises(ValidationError):
        MessageResponse(
            id=uuid4(),
            conversationId=uuid4(),
            role=MessageRole.ASSISTANT,
            content="State is local. [1]",
            status=MessageStatus.COMPLETED,
            createdAt=datetime.now(UTC),
        )


def test_message_response_serializes_content_and_citations() -> None:
    payload = MessageResponse(
        id=uuid4(),
        conversationId=uuid4(),
        role=MessageRole.ASSISTANT,
        content="State is local. [1]",
        status=MessageStatus.COMPLETED,
        createdAt=datetime.now(UTC),
        citations=[
            CitationRecord(
                citation_id="1",
                source_path="state.md",
                heading="State",
                chunk_text="State belongs to a component.",
            )
        ],
    )

    serialized = payload.model_dump(mode="json", by_alias=True)
    assert set(serialized) == {
        "id",
        "conversationId",
        "role",
        "content",
        "status",
        "createdAt",
        "citations",
    }
    assert serialized["citations"] == [
        {
            "citationId": "1",
            "sourcePath": "state.md",
            "heading": "State",
            "chunkText": "State belongs to a component.",
        }
    ]
