import pytest

from backend.auth.models import UserAccount
from backend.auth.repository import UserAccountRepository
from backend.auth.schemas import UserRole


@pytest.mark.asyncio
async def test_create_persists_clerk_name_projection() -> None:
    session = FakeSession()

    user = await UserAccountRepository().create(
        session,
        clerk_id="user_123",
        role=UserRole.INSTRUCTOR,
        first_name="Person",
        last_name="OneTwoThree",
    )

    assert user.clerk_id == "user_123"
    assert user.first_name == "Person"
    assert user.last_name == "OneTwoThree"
    assert user.role == UserRole.INSTRUCTOR.value
    assert session.added == [user]
    assert session.flushes == 1


@pytest.mark.asyncio
async def test_update_profile_projection_flushes_when_names_change() -> None:
    user = UserAccount(
        clerk_id="user_123",
        first_name="Old",
        last_name="Name",
        role=UserRole.STUDENT.value,
    )
    session = FakeSession()

    changed = await UserAccountRepository().update_profile_projection(
        session,
        user=user,
        first_name="New",
        last_name="Name",
    )

    assert changed is True
    assert user.first_name == "New"
    assert user.last_name == "Name"
    assert session.flushes == 1


@pytest.mark.asyncio
async def test_update_profile_projection_skips_unchanged_names() -> None:
    user = UserAccount(
        clerk_id="user_123",
        first_name="Same",
        last_name="Name",
        role=UserRole.STUDENT.value,
    )
    session = FakeSession()

    changed = await UserAccountRepository().update_profile_projection(
        session,
        user=user,
        first_name="Same",
        last_name="Name",
    )

    assert changed is False
    assert session.flushes == 0


class FakeSession:
    def __init__(self, user: UserAccount | None = None) -> None:
        self.user = user
        self.added = []
        self.flushes = 0

    def add(self, user: UserAccount) -> None:
        self.added.append(user)
        self.user = user

    async def flush(self) -> None:
        self.flushes += 1

    async def scalar(self, statement) -> UserAccount | None:
        return self.user
