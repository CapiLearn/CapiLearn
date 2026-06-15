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
            "email": " jane@example.com ",
        }
    )

    assert profile.display_name == "Jane Doe"
    assert profile.email == "jane@example.com"


def test_profile_from_clerk_user_selects_primary_email_and_converts_timestamps() -> None:
    profile = profile_from_clerk_user(
        {
            "id": "user_123",
            "first_name": " Jane ",
            "last_name": " Doe ",
            "primary_email_address_id": "email_primary",
            "email_addresses": [
                {"id": "email_other", "email_address": "other@example.com"},
                {"id": "email_primary", "email_address": " primary@example.com "},
            ],
            "updated_at": 1781539200123,
        }
    )

    assert profile.clerk_id == "user_123"
    assert profile.display_name == "Jane Doe"
    assert profile.email == "primary@example.com"
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


def test_profile_from_clerk_user_rejects_unmatched_primary_email_id() -> None:
    with pytest.raises(ApiError) as exc_info:
        profile_from_clerk_user(
            {
                "id": "user_123",
                "first_name": "Jane",
                "last_name": "Doe",
                "primary_email_address_id": "missing",
                "email_addresses": [{"id": "email_other", "email_address": "other@example.com"}],
                "updated_at": 1781539200000,
            }
        )

    assert exc_info.value.code == "invalid_clerk_profile"
    assert exc_info.value.status_code == 422


@pytest.mark.parametrize("primary_email_address_id", [" ", 123, True])
def test_profile_from_clerk_user_rejects_invalid_primary_email_id(
    primary_email_address_id: object,
) -> None:
    with pytest.raises(ApiError) as exc_info:
        profile_from_clerk_user(
            {
                "id": "user_123",
                "first_name": "Jane",
                "last_name": "Doe",
                "primary_email_address_id": primary_email_address_id,
                "email_addresses": [{"id": "email_primary", "email_address": "jane@example.com"}],
                "updated_at": 1781539200000,
            }
        )

    assert exc_info.value.code == "invalid_clerk_profile"
    assert exc_info.value.status_code == 422


def test_profile_from_clerk_user_rejects_non_list_email_addresses_for_primary_email() -> None:
    with pytest.raises(ApiError) as exc_info:
        profile_from_clerk_user(
            {
                "id": "user_123",
                "first_name": "Jane",
                "last_name": "Doe",
                "primary_email_address_id": "email_primary",
                "email_addresses": {"id": "email_primary", "email_address": "jane@example.com"},
                "updated_at": 1781539200000,
            }
        )

    assert exc_info.value.code == "invalid_clerk_profile"
    assert exc_info.value.status_code == 422


@pytest.mark.parametrize(
    "email_item",
    [{"id": "email_primary"}, {"id": "email_primary", "email_address": " "}],
)
def test_profile_from_clerk_user_rejects_matching_primary_email_without_valid_address(
    email_item: dict[str, object],
) -> None:
    with pytest.raises(ApiError) as exc_info:
        profile_from_clerk_user(
            {
                "id": "user_123",
                "first_name": "Jane",
                "last_name": "Doe",
                "primary_email_address_id": "email_primary",
                "email_addresses": [email_item],
                "updated_at": 1781539200000,
            }
        )

    assert exc_info.value.code == "invalid_clerk_profile"
    assert exc_info.value.status_code == 422


@pytest.mark.parametrize("payload", [{}, {"primary_email_address_id": None}])
def test_profile_from_clerk_user_without_primary_email_returns_no_email(
    payload: dict[str, object],
) -> None:
    profile = profile_from_clerk_user(
        {
            "id": "user_123",
            "first_name": "Jane",
            "last_name": "Doe",
            "email_addresses": [{"id": "email_other", "email_address": "other@example.com"}],
            "updated_at": 1781539200000,
            **payload,
        }
    )

    assert profile.email is None
    assert profile.clerk_profile_updated_at == datetime(2026, 6, 15, 16, 0, tzinfo=UTC)


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
