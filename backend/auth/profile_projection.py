from dataclasses import dataclass
from typing import Any

from fastapi import status

from backend.core.exceptions import ApiError

PROFILE_INCOMPLETE_ERROR = "Complete your profile before using the app."


@dataclass(frozen=True)
class ParsedClerkProfile:
    first_name: str
    last_name: str


def profile_from_clerk_payload(payload: dict[str, Any]) -> ParsedClerkProfile:
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


def _normalized_string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
