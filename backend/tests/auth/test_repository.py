from uuid import uuid4

from backend.auth.models import UserAccount
from backend.auth.repository import UserAccountRepository
from backend.auth.schemas import UserRole


def test_apply_profile_claims_updates_email_and_display_name_without_changing_role() -> None:
    user = UserAccount(
        id=uuid4(),
        clerk_id="user_123",
        email="old@example.com",
        display_name="Old Name",
        role=UserRole.STUDENT.value,
    )

    changed = UserAccountRepository().apply_profile_claims(
        user,
        email="new@example.com",
        display_name="New Name",
    )

    assert changed is True
    assert user.email == "new@example.com"
    assert user.display_name == "New Name"
    assert user.role == UserRole.STUDENT.value


def test_apply_profile_claims_returns_false_for_unchanged_values() -> None:
    user = UserAccount(
        id=uuid4(),
        clerk_id="user_123",
        email="same@example.com",
        display_name="Same Name",
        role=UserRole.INSTRUCTOR.value,
    )

    changed = UserAccountRepository().apply_profile_claims(
        user,
        email="same@example.com",
        display_name="Same Name",
    )

    assert changed is False
    assert user.email == "same@example.com"
    assert user.display_name == "Same Name"
    assert user.role == UserRole.INSTRUCTOR.value


def test_apply_profile_claims_does_not_overwrite_profile_with_none_values() -> None:
    user = UserAccount(
        id=uuid4(),
        clerk_id="user_123",
        email="kept@example.com",
        display_name="Kept Name",
        role=UserRole.STUDENT.value,
    )

    changed = UserAccountRepository().apply_profile_claims(
        user,
        email=None,
        display_name=None,
    )

    assert changed is False
    assert user.email == "kept@example.com"
    assert user.display_name == "Kept Name"
    assert user.role == UserRole.STUDENT.value
