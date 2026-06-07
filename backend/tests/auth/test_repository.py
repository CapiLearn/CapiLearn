from inspect import signature

import pytest

from backend.auth.models import UserAccount
from backend.auth.repository import UserAccountRepository
from backend.auth.schemas import UserRole


def test_repository_does_not_expose_profile_merge_behavior() -> None:
    assert not hasattr(UserAccountRepository, "apply_profile_claims")

    create_parameters = signature(UserAccountRepository.create).parameters
    assert "email" not in create_parameters
    assert "display_name" not in create_parameters


@pytest.mark.asyncio
async def test_create_persists_only_app_owned_auth_state() -> None:
    session = FakeSession()

    user = await UserAccountRepository().create(
        session,
        clerk_id="user_123",
        role=UserRole.INSTRUCTOR,
    )

    assert user.clerk_id == "user_123"
    assert user.role == UserRole.INSTRUCTOR.value
    assert not hasattr(user, "email")
    assert not hasattr(user, "display_name")
    assert session.added == [user]
    assert session.flushes == 1


class FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.flushes = 0

    def add(self, user: UserAccount) -> None:
        self.added.append(user)

    async def flush(self) -> None:
        self.flushes += 1
