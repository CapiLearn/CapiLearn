from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import status

from backend.core.exceptions import ApiError

PROFILE_INCOMPLETE_ERROR = "Complete your profile before using the app."


@dataclass(frozen=True)
class ParsedClerkProfile:
    email: str | None
    display_name: str


@dataclass(frozen=True)
class ClerkProfileSnapshot:
    clerk_id: str
    display_name: str
    email: str | None
    clerk_profile_updated_at: datetime


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

    return ParsedClerkProfile(
        email=_normalized_string(payload.get("email")),
        display_name=f"{first_name} {last_name}",
    )


def profile_from_clerk_user(data: dict[str, object]) -> ClerkProfileSnapshot:
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
        display_name=f"{first_name} {last_name}",
        email=_primary_email(data),
        clerk_profile_updated_at=_clerk_millis_to_datetime(data.get("updated_at")),
    )


def _normalized_string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _primary_email(data: dict[str, object]) -> str | None:
    if "primary_email_address_id" not in data or data["primary_email_address_id"] is None:
        return None

    primary_email_address_id_value = data["primary_email_address_id"]
    if not isinstance(primary_email_address_id_value, str):
        raise _invalid_clerk_profile("Clerk user payload primary email is missing or invalid.")

    primary_email_address_id = _normalized_string(primary_email_address_id_value)
    if primary_email_address_id is None:
        raise _invalid_clerk_profile("Clerk user payload primary email is missing or invalid.")

    email_addresses = data.get("email_addresses")
    if not isinstance(email_addresses, list):
        raise _invalid_clerk_profile("Clerk user payload primary email is missing or invalid.")

    for item in email_addresses:
        if not isinstance(item, dict):
            continue
        if item.get("id") == primary_email_address_id:
            email = _normalized_string(item.get("email_address"))
            if email is None:
                raise _invalid_clerk_profile(
                    "Clerk user payload primary email is missing or invalid."
                )
            return email

    raise _invalid_clerk_profile("Clerk user payload primary email is missing or invalid.")


def _invalid_clerk_profile(message: str) -> ApiError:
    return ApiError(
        code="invalid_clerk_profile",
        message=message,
        status_code=422,
    )


def _clerk_millis_to_datetime(value: object) -> datetime:
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
