import pytest

from backend.auth.profile_projection import profile_from_clerk_payload
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


@pytest.mark.parametrize(
    "payload",
    [
        {"last_name": "Doe"},
        {"first_name": "Jane"},
    ],
)
def test_profile_from_clerk_payload_rejects_missing_required_name_claims(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ApiError) as exc_info:
        profile_from_clerk_payload(payload)

    assert exc_info.value.code == "profile_incomplete"
