"""Translate Clerk profile payloads into validated local profile snapshots."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import status

from backend.core.exceptions import ApiError

PROFILE_INCOMPLETE_ERROR = "Complete your profile before using the app."


@dataclass(frozen=True)
class ParsedClerkProfile:
    """Profile fields required from a Clerk session token."""

    first_name: str
    last_name: str


@dataclass(frozen=True)
class ClerkProfileSnapshot:
    """Profile fields required from a Clerk user webhook payload."""

    clerk_id: str
    first_name: str
    last_name: str
    clerk_profile_updated_at: datetime


def profile_from_clerk_payload(payload: dict[str, Any]) -> ParsedClerkProfile:
    """Validate profile claims from a Clerk session token."""
    # Clerk sign-up requires first and last name, and our session token template
    # must expose both claims. Missing values mean that contract is misconfigured.
    first_name = _normalized_string(payload.get("first_name"))
    last_name = _normalized_string(payload.get("last_name"))
    if first_name is None or last_name is None:
        raise ApiError(
            code="profile_incomplete",
            message=PROFILE_INCOMPLETE_ERROR,
            status_code=status.HTTP_409_CONFLICT,
        )

    return ParsedClerkProfile(first_name=first_name, last_name=last_name)


def profile_from_clerk_user(data: dict[str, object]) -> ClerkProfileSnapshot:
    """Validate the Clerk user object carried by user lifecycle webhooks."""
    clerk_id = _normalized_string(data.get("id"))
    if clerk_id is None:
        raise ApiError(
            code="invalid_clerk_profile",
            message="Clerk user payload is missing a user id.",
            status_code=422,
        )

    first_name = _normalized_string(data.get("first_name"))
    last_name = _normalized_string(data.get("last_name"))
    if first_name is None or last_name is None:
        raise ApiError(
            code="profile_incomplete",
            message=PROFILE_INCOMPLETE_ERROR,
            status_code=status.HTTP_409_CONFLICT,
        )

    return ClerkProfileSnapshot(
        clerk_id=clerk_id,
        first_name=first_name,
        last_name=last_name,
        clerk_profile_updated_at=_clerk_millis_to_datetime(data.get("updated_at")),
    )


def _normalized_string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _clerk_millis_to_datetime(value: object) -> datetime:
    # bool is an int subclass, but it is not a valid Clerk millisecond timestamp.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ApiError(
            code="invalid_clerk_profile",
            message="Clerk user payload is missing or has malformed updated_at.",
            status_code=422,
        )
    try:
        return datetime.fromtimestamp(value / 1000, tz=UTC)
    except (OSError, OverflowError, ValueError) as exc:
        raise ApiError(
            code="invalid_clerk_profile",
            message="Clerk user payload has malformed updated_at.",
            status_code=422,
        ) from exc
