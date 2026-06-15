from datetime import UTC, datetime

import pytest
from sqlalchemy.dialects import postgresql

from backend.auth.models import UserAccount
from backend.auth.repository import UserAccountRepository
from backend.auth.schemas import UserRole


@pytest.mark.asyncio
async def test_create_requires_and_persists_profile_projection() -> None:
    session = FakeSession()

    user = await UserAccountRepository().create(
        session,
        clerk_id="user_123",
        role=UserRole.INSTRUCTOR,
        display_name="Person 123",
        email="person@example.com",
        profile_synced_at=datetime(2026, 6, 15, tzinfo=UTC),
    )

    assert user.clerk_id == "user_123"
    assert user.display_name == "Person 123"
    assert user.email == "person@example.com"
    assert user.profile_synced_at == datetime(2026, 6, 15, tzinfo=UTC)
    assert user.role == UserRole.INSTRUCTOR.value
    assert session.added == [user]
    assert session.flushes == 1


@pytest.mark.asyncio
async def test_update_profile_projection_flushes_when_profile_values_change() -> None:
    synced_at = datetime(2026, 6, 15, tzinfo=UTC)
    user = UserAccount(
        clerk_id="user_123",
        display_name="Old Name",
        email="old@example.com",
        profile_synced_at=datetime(2026, 6, 1, tzinfo=UTC),
        role=UserRole.STUDENT.value,
    )
    session = FakeSession()

    changed = await UserAccountRepository().update_profile_projection(
        session,
        user=user,
        display_name="New Name",
        email="new@example.com",
        synced_at=synced_at,
    )

    assert changed is True
    assert user.display_name == "New Name"
    assert user.email == "new@example.com"
    assert user.profile_synced_at == synced_at
    assert session.flushes == 1


@pytest.mark.asyncio
async def test_update_profile_projection_allows_nullable_email_but_not_display_name() -> None:
    synced_at = datetime(2026, 6, 15, tzinfo=UTC)
    user = UserAccount(
        clerk_id="user_123",
        display_name="Old Name",
        email="old@example.com",
        profile_synced_at=datetime(2026, 6, 1, tzinfo=UTC),
        role=UserRole.STUDENT.value,
    )
    session = FakeSession()

    changed = await UserAccountRepository().update_profile_projection(
        session,
        user=user,
        display_name="New Name",
        email=None,
        synced_at=synced_at,
    )

    assert changed is True
    assert user.display_name == "New Name"
    assert user.email is None
    assert user.profile_synced_at == synced_at
    assert session.flushes == 1


@pytest.mark.asyncio
async def test_update_profile_projection_skips_unchanged_profile_values() -> None:
    synced_at = datetime(2026, 6, 15, tzinfo=UTC)
    original_synced_at = datetime(2026, 6, 1, tzinfo=UTC)
    user = UserAccount(
        clerk_id="user_123",
        display_name="Same Name",
        email=None,
        profile_synced_at=original_synced_at,
        role=UserRole.STUDENT.value,
    )
    session = FakeSession()

    changed = await UserAccountRepository().update_profile_projection(
        session,
        user=user,
        display_name="Same Name",
        email=None,
        synced_at=synced_at,
    )

    assert changed is False
    assert user.profile_synced_at == original_synced_at
    assert session.flushes == 0


@pytest.mark.asyncio
async def test_upsert_from_clerk_profile_creates_student_without_role_claims() -> None:
    synced_at = datetime(2026, 6, 15, tzinfo=UTC)
    clerk_updated_at = datetime(2026, 6, 14, tzinfo=UTC)
    result_user = UserAccount(
        clerk_id="user_123",
        role=UserRole.STUDENT.value,
        display_name="New User",
        email="new@example.com",
        profile_synced_at=synced_at,
        clerk_profile_updated_at=clerk_updated_at,
    )
    session = StatementCaptureSession(result_user=result_user)

    user = await UserAccountRepository().upsert_from_clerk_profile(
        session,
        clerk_id="user_123",
        display_name="New User",
        email="new@example.com",
        clerk_profile_updated_at=clerk_updated_at,
        synced_at=synced_at,
    )

    assert user is result_user
    assert session.added == []
    assert session.flushes == 0

    sql = _compiled_sql(session.statements[0])
    assert "INSERT INTO user_account" in sql
    assert "ON CONFLICT (clerk_id) DO UPDATE SET" in sql
    assert "RETURNING user_account.id" in sql
    assert "SELECT" not in sql
    params = _compiled_params(session.statements[0])
    assert params["clerk_id"] == "user_123"
    assert params["role"] == UserRole.STUDENT.value
    assert params["display_name"] == "New User"
    assert params["email"] == "new@example.com"
    assert params["profile_synced_at"] == synced_at
    assert params["clerk_profile_updated_at"] == clerk_updated_at


@pytest.mark.asyncio
async def test_upsert_from_clerk_profile_statement_preserves_role_and_soft_delete() -> None:
    synced_at = datetime(2026, 6, 15, tzinfo=UTC)
    clerk_updated_at = datetime(2026, 6, 14, tzinfo=UTC)
    result_user = UserAccount(
        clerk_id="user_123",
        display_name="Old User",
        email="old@example.com",
        profile_synced_at=datetime(2026, 6, 1, tzinfo=UTC),
        clerk_profile_updated_at=datetime(2026, 6, 1, tzinfo=UTC),
        role=UserRole.ADMIN.value,
        deleted_at=datetime(2026, 6, 2, tzinfo=UTC),
    )
    session = StatementCaptureSession(result_user=result_user)

    updated = await UserAccountRepository().upsert_from_clerk_profile(
        session,
        clerk_id="user_123",
        display_name="New User",
        email=None,
        clerk_profile_updated_at=clerk_updated_at,
        synced_at=synced_at,
    )

    assert updated is result_user
    assert session.flushes == 0

    update_sql = _update_clause(session.statements[0])
    assert "display_name = CASE" in update_sql
    assert "email = CASE" in update_sql
    assert "profile_synced_at = CASE" in update_sql
    assert "clerk_profile_updated_at = CASE" in update_sql
    assert "updated_at = CASE" in update_sql
    assert "role = " not in update_sql
    assert "deleted_at = " not in update_sql


@pytest.mark.asyncio
async def test_upsert_from_clerk_profile_statement_encodes_timestamp_freshness() -> None:
    result_user = UserAccount(
        clerk_id="user_123",
        display_name="Current User",
        email="current@example.com",
        profile_synced_at=datetime(2026, 6, 15, tzinfo=UTC),
        clerk_profile_updated_at=datetime(2026, 6, 14, tzinfo=UTC),
        role=UserRole.ADMIN.value,
    )
    session = StatementCaptureSession(result_user=result_user)

    updated = await UserAccountRepository().upsert_from_clerk_profile(
        session,
        clerk_id="user_123",
        display_name="Old User",
        email="old@example.com",
        clerk_profile_updated_at=datetime(2026, 6, 1, tzinfo=UTC),
        synced_at=datetime(2026, 6, 16, tzinfo=UTC),
    )

    assert updated is result_user
    assert session.flushes == 0
    update_sql = _update_clause(session.statements[0])
    assert "user_account.clerk_profile_updated_at IS NULL" in update_sql
    assert "excluded.clerk_profile_updated_at IS NOT NULL" not in update_sql
    assert (
        "excluded.clerk_profile_updated_at >= user_account.clerk_profile_updated_at" in update_sql
    )
    assert " WHERE " not in update_sql


@pytest.mark.asyncio
async def test_upsert_from_clerk_profile_statement_applies_when_stored_timestamp_missing() -> None:
    clerk_updated_at = datetime(2026, 6, 16, tzinfo=UTC)
    result_user = UserAccount(
        clerk_id="user_123",
        display_name="Timestamped User",
        email="timestamped@example.com",
        profile_synced_at=datetime(2026, 6, 15, tzinfo=UTC),
        clerk_profile_updated_at=None,
        role=UserRole.ADMIN.value,
    )
    session = StatementCaptureSession(result_user=result_user)

    updated = await UserAccountRepository().upsert_from_clerk_profile(
        session,
        clerk_id="user_123",
        display_name="Timestamped User",
        email="timestamped@example.com",
        clerk_profile_updated_at=clerk_updated_at,
        synced_at=datetime(2026, 6, 16, tzinfo=UTC),
    )

    assert updated is result_user

    sql = _compiled_sql(session.statements[0])
    assert "user_account.clerk_profile_updated_at IS NULL" in sql
    assert "excluded.clerk_profile_updated_at IS NOT NULL" not in sql


@pytest.mark.asyncio
async def test_upsert_from_clerk_profile_statement_allows_soft_deleted_profile_updates() -> None:
    synced_at = datetime(2026, 6, 15, tzinfo=UTC)
    result_user = UserAccount(
        clerk_id="user_123",
        display_name="Soft Deleted User",
        email="soft-deleted@example.com",
        profile_synced_at=datetime(2026, 6, 1, tzinfo=UTC),
        clerk_profile_updated_at=None,
        role=UserRole.ADMIN.value,
        deleted_at=datetime(2026, 6, 2, tzinfo=UTC),
    )
    session = StatementCaptureSession(result_user=result_user)

    updated = await UserAccountRepository().upsert_from_clerk_profile(
        session,
        clerk_id="user_123",
        display_name="Updated Soft Deleted User",
        email="updated@example.com",
        clerk_profile_updated_at=datetime(2026, 6, 14, tzinfo=UTC),
        synced_at=synced_at,
    )

    assert updated is result_user
    update_sql = _update_clause(session.statements[0])
    assert "display_name = CASE" in update_sql
    assert "email = CASE" in update_sql
    assert "profile_synced_at = CASE" in update_sql
    assert "deleted_at = " not in update_sql


@pytest.mark.asyncio
async def test_soft_delete_by_clerk_id_sets_deleted_at_once() -> None:
    deleted_at = datetime(2026, 6, 15, tzinfo=UTC)
    user = UserAccount(
        clerk_id="user_123",
        display_name="User",
        profile_synced_at=datetime(2026, 6, 1, tzinfo=UTC),
        role=UserRole.STUDENT.value,
    )
    session = FakeSession(user=user)

    deleted = await UserAccountRepository().soft_delete_by_clerk_id(
        session,
        clerk_id="user_123",
        deleted_at=deleted_at,
    )
    replay_deleted = await UserAccountRepository().soft_delete_by_clerk_id(
        session,
        clerk_id="user_123",
        deleted_at=datetime(2026, 6, 16, tzinfo=UTC),
    )

    assert deleted is True
    assert replay_deleted is False
    assert user.deleted_at == deleted_at
    assert session.flushes == 1


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


class StatementCaptureSession(FakeSession):
    def __init__(self, *, result_user: UserAccount) -> None:
        super().__init__(user=result_user)
        self.statements = []
        self._result_user = result_user

    async def execute(self, statement):
        self.statements.append(statement)
        return ScalarResult(self._result_user)


class ScalarResult:
    def __init__(self, value: UserAccount) -> None:
        self._value = value

    def scalar_one(self) -> UserAccount:
        return self._value


def _compiled_sql(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": False},
        )
    )


def _compiled_params(statement) -> dict:
    return statement.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": False},
    ).params


def _update_clause(statement) -> str:
    return (
        _compiled_sql(statement)
        .split("DO UPDATE SET", 1)[1]
        .split(
            " RETURNING",
            1,
        )[0]
    )
