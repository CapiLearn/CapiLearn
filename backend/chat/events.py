from enum import StrEnum
import json
from typing import Annotated, Any, Literal, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from pydantic.alias_generators import to_camel

from backend.llm.schemas import Citation


class ChatStreamEvent(StrEnum):
    CONVERSATION_CREATED = "conversation_created"
    USER_MESSAGE_CREATED = "user_message_created"
    ASSISTANT_MESSAGE_CREATED = "assistant_message_created"
    DELTA = "delta"
    CITATIONS = "citations"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    ERROR = "error"


class ChatStreamPayload(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class ConversationCreatedPayload(ChatStreamPayload):
    type: Literal["conversation_created"] = "conversation_created"
    conversation_id: UUID
    title: str | None


class UserMessageCreatedPayload(ChatStreamPayload):
    type: Literal["user_message_created"] = "user_message_created"
    message_id: UUID
    conversation_id: UUID


class AssistantMessageCreatedPayload(ChatStreamPayload):
    type: Literal["assistant_message_created"] = "assistant_message_created"
    message_id: UUID
    conversation_id: UUID
    status: Literal["streaming"]


class DeltaPayload(ChatStreamPayload):
    type: Literal["delta"] = "delta"
    message_id: UUID
    text: str


class CitationsPayload(ChatStreamPayload):
    type: Literal["citations"] = "citations"
    message_id: UUID
    citations: list[Citation]


class CompletedPayload(ChatStreamPayload):
    type: Literal["completed"] = "completed"
    message_id: UUID
    status: Literal["completed"]
    finish_reason: str | None = None


class BlockedPayload(ChatStreamPayload):
    type: Literal["blocked"] = "blocked"
    message_id: UUID
    status: Literal["blocked"]
    reason: str


class ErrorPayload(ChatStreamPayload):
    type: Literal["error"] = "error"
    code: str
    message: str
    details: dict[str, Any] | None = None


ChatStreamPayloadUnion: TypeAlias = Annotated[
    ConversationCreatedPayload
    | UserMessageCreatedPayload
    | AssistantMessageCreatedPayload
    | DeltaPayload
    | CitationsPayload
    | CompletedPayload
    | BlockedPayload
    | ErrorPayload,
    Field(discriminator="type"),
]


def _chat_stream_payload_schema() -> dict[str, Any]:
    schema = TypeAdapter(ChatStreamPayloadUnion).json_schema()
    definitions = schema.pop("$defs", {})
    schema = _inline_schema_refs(schema, definitions, seen=set())
    for option in schema.get("oneOf", []):
        if isinstance(option, dict):
            required = option.setdefault("required", [])
            if "type" not in required:
                required.append("type")
    schema["discriminator"] = {"propertyName": "type"}
    return schema


def _inline_schema_refs(
    value: Any,
    definitions: dict[str, Any],
    *,
    seen: set[str],
) -> Any:
    if isinstance(value, list):
        return [_inline_schema_refs(item, definitions, seen=seen) for item in value]
    if not isinstance(value, dict):
        return value

    ref = value.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        name = ref.rsplit("/", maxsplit=1)[-1]
        if name in seen:
            return value
        return _inline_schema_refs(
            definitions[name],
            definitions,
            seen=seen | {name},
        )

    return {
        key: _inline_schema_refs(item, definitions, seen=seen)
        for key, item in value.items()
        if key != "$defs"
    }


CHAT_STREAM_RESPONSE = {
    200: {
        "description": "Server-sent chat events. Each data frame contains JSON.",
        "content": {
            "text/event-stream": {
                "schema": _chat_stream_payload_schema(),
            },
        },
    },
}


def sse_event(data: ChatStreamPayloadUnion) -> dict[str, str]:
    payload = data.model_dump(mode="json", by_alias=True)
    return {"event": data.type, "data": json.dumps(payload)}
