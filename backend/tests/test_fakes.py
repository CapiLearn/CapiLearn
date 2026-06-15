from datetime import UTC, datetime
from uuid import uuid4

import pytest

from backend.auth.models import UserAccount
from backend.auth.schemas import UserRole
from backend.tests.fakes import FakeUserRepository


@pytest.mark.asyncio
async def test_fake_user_repository_rejects_mismatched_clerk_lookup() -> None:
    repository = FakeUserRepository(user=_user(clerk_id="user_stored"))

    with pytest.raises(AssertionError):
        await repository.get_by_clerk_id(object(), clerk_id="user_other")


@pytest.mark.asyncio
async def test_fake_user_repository_rejects_mismatched_queued_clerk_lookup() -> None:
    repository = FakeUserRepository(lookup_results=[_user(clerk_id="user_stored")])

    with pytest.raises(AssertionError):
        await repository.get_by_clerk_id(object(), clerk_id="user_other")


def _user(
    *,
    clerk_id: str,
    display_name: str = "Stored User",
    email: str | None = None,
    profile_synced_at: datetime | None = None,
    clerk_profile_updated_at: datetime | None = None,
) -> UserAccount:
    return UserAccount(
        id=uuid4(),
        clerk_id=clerk_id,
        role=UserRole.STUDENT.value,
        display_name=display_name,
        email=email,
        profile_synced_at=profile_synced_at or datetime(2026, 6, 1, tzinfo=UTC),
        clerk_profile_updated_at=clerk_profile_updated_at,
    )
