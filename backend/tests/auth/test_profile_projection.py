from datetime import UTC, datetime

import pytest
from fastapi import status

from backend.auth.profile_projection import (
    profile_from_clerk_payload,
    profile_from_clerk_user,
)
from backend.core.exceptions import ApiError


def test_profile_from_clerk_payload_uses_required_name_claims() -> None:
    profile = profile_from_clerk_payload(
        {
            "first_name": " Jane ",
            "last_name": " Doe ",
        }
    )

    assert profile.first_name == "Jane"
    assert profile.last_name == "Doe"


def test_profile_from_clerk_user_extracts_names_and_converts_timestamps() -> None:
    profile = profile_from_clerk_user(
        {
            "id": "user_123",
            "first_name": " Jane ",
            "last_name": " Doe ",
            "updated_at": 1781539200123,
        }
    )

    assert profile.clerk_id == "user_123"
    assert profile.first_name == "Jane"
    assert profile.last_name == "Doe"
    assert profile.clerk_profile_updated_at == datetime(
        2026,
        6,
        15,
        16,
        0,
        0,
        123000,
        tzinfo=UTC,
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"first_name": "Jane", "last_name": "Doe"},
        {"id": "user_123", "last_name": "Doe"},
        {"id": "user_123", "first_name": "Jane"},
    ],
)
def test_profile_from_clerk_user_rejects_missing_required_fields(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ApiError) as exc_info:
        profile_from_clerk_user(payload)

    assert exc_info.value.status_code in {
        status.HTTP_409_CONFLICT,
        422,
    }


@pytest.mark.parametrize("updated_at", [None, "1781539200000", 1781539200000.0, True])
def test_profile_from_clerk_user_rejects_missing_or_non_int_updated_at(
    updated_at: object,
) -> None:
    payload = {
        "id": "user_123",
        "first_name": "Jane",
        "last_name": "Doe",
        "updated_at": updated_at,
    }

    with pytest.raises(ApiError) as exc_info:
        profile_from_clerk_user(payload)

    assert exc_info.value.code == "invalid_clerk_profile"
    assert exc_info.value.status_code == 422
