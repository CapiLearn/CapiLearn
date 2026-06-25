from datetime import UTC, datetime

import pytest
from sqlalchemy.dialects import postgresql

from backend.auth.models import UserAccount
from backend.auth.repository import UserAccountRepository
from backend.auth.schemas import UserRole


@pytest.mark.asyncio
async def test_create_or_get_by_clerk_id_inserts_with_conflict_do_nothing() -> None:
    result_user = UserAccount(
        clerk_id="user_123",
        first_name="New",
        last_name="User",
        role=UserRole.ADMIN.value,
    )
    session = StatementCaptureSession(result_user=result_user)

    user, created = await UserAccountRepository().create_or_get_by_clerk_id(
        session,
        clerk_id="user_123",
        role=UserRole.ADMIN,
        first_name="New",
        last_name="User",
    )

    assert user is result_user
    assert created is True
    assert session.added == []
    assert session.flushes == 0
    assert session.scalar_statements == []

    sql = _compiled_sql(session.statements[0])
    assert "INSERT INTO user_account" in sql
    assert "ON CONFLICT (clerk_id) DO NOTHING" in sql
    assert "RETURNING user_account.id" in sql
    assert " DO UPDATE SET " not in sql
    params = _compiled_params(session.statements[0])
    assert params["clerk_id"] == "user_123"
    assert params["role"] == UserRole.ADMIN.value
    assert params["first_name"] == "New"
    assert params["last_name"] == "User"


@pytest.mark.asyncio
async def test_create_or_get_by_clerk_id_returns_existing_user_after_conflict() -> None:
    existing_user = UserAccount(
        clerk_id="user_123",
        first_name="Existing",
        last_name="User",
        role=UserRole.STUDENT.value,
    )
    session = StatementCaptureSession(result_user=None, user=existing_user)

    user, created = await UserAccountRepository().create_or_get_by_clerk_id(
        session,
        clerk_id="user_123",
        role=UserRole.ADMIN,
        first_name="New",
        last_name="User",
    )

    assert user is existing_user
    assert created is False
    assert len(session.statements) == 1
    assert len(session.scalar_statements) == 1


@pytest.mark.asyncio
async def test_create_or_get_by_clerk_id_requires_existing_user_after_conflict() -> None:
    session = StatementCaptureSession(result_user=None)

    with pytest.raises(RuntimeError, match="Expected existing user_account"):
        await UserAccountRepository().create_or_get_by_clerk_id(
            session,
            clerk_id="user_missing",
            role=UserRole.STUDENT,
            first_name="Missing",
            last_name="User",
        )

    assert len(session.statements) == 1
    assert len(session.scalar_statements) == 1


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


@pytest.mark.asyncio
async def test_upsert_from_clerk_profile_creates_student_without_role_claims() -> None:
    clerk_updated_at = datetime(2026, 6, 14, tzinfo=UTC)
    result_user = UserAccount(
        clerk_id="user_123",
        role=UserRole.STUDENT.value,
        first_name="New",
        last_name="User",
        clerk_profile_updated_at=clerk_updated_at,
    )
    session = StatementCaptureSession(result_user=result_user)

    user = await UserAccountRepository().upsert_from_clerk_profile(
        session,
        clerk_id="user_123",
        first_name="New",
        last_name="User",
        clerk_profile_updated_at=clerk_updated_at,
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
    assert params["first_name"] == "New"
    assert params["last_name"] == "User"
    assert params["clerk_profile_updated_at"] == clerk_updated_at


@pytest.mark.asyncio
async def test_upsert_from_clerk_profile_statement_preserves_role_and_soft_delete() -> None:
    clerk_updated_at = datetime(2026, 6, 14, tzinfo=UTC)
    result_user = UserAccount(
        clerk_id="user_123",
        first_name="Old",
        last_name="User",
        clerk_profile_updated_at=datetime(2026, 6, 1, tzinfo=UTC),
        role=UserRole.ADMIN.value,
        deleted_at=datetime(2026, 6, 2, tzinfo=UTC),
    )
    session = StatementCaptureSession(result_user=result_user)

    updated = await UserAccountRepository().upsert_from_clerk_profile(
        session,
        clerk_id="user_123",
        first_name="New",
        last_name="User",
        clerk_profile_updated_at=clerk_updated_at,
    )

    assert updated is result_user
    assert session.flushes == 0

    update_sql = _update_clause(session.statements[0])
    assert "first_name = CASE" in update_sql
    assert "last_name = CASE" in update_sql
    assert "clerk_profile_updated_at = CASE" in update_sql
    assert "updated_at = CASE" in update_sql
    assert "role = " not in update_sql
    assert "deleted_at = " not in update_sql


@pytest.mark.asyncio
async def test_upsert_from_clerk_profile_statement_encodes_timestamp_freshness() -> None:
    result_user = UserAccount(
        clerk_id="user_123",
        first_name="Current",
        last_name="User",
        clerk_profile_updated_at=datetime(2026, 6, 14, tzinfo=UTC),
        role=UserRole.ADMIN.value,
    )
    session = StatementCaptureSession(result_user=result_user)

    updated = await UserAccountRepository().upsert_from_clerk_profile(
        session,
        clerk_id="user_123",
        first_name="Old",
        last_name="User",
        clerk_profile_updated_at=datetime(2026, 6, 1, tzinfo=UTC),
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
        first_name="Timestamped",
        last_name="User",
        clerk_profile_updated_at=None,
        role=UserRole.ADMIN.value,
    )
    session = StatementCaptureSession(result_user=result_user)

    updated = await UserAccountRepository().upsert_from_clerk_profile(
        session,
        clerk_id="user_123",
        first_name="Timestamped",
        last_name="User",
        clerk_profile_updated_at=clerk_updated_at,
    )

    assert updated is result_user

    sql = _compiled_sql(session.statements[0])
    assert "user_account.clerk_profile_updated_at IS NULL" in sql
    assert "excluded.clerk_profile_updated_at IS NOT NULL" not in sql


@pytest.mark.asyncio
async def test_upsert_from_clerk_profile_statement_allows_soft_deleted_profile_updates() -> None:
    result_user = UserAccount(
        clerk_id="user_123",
        first_name="Soft",
        last_name="Deleted",
        clerk_profile_updated_at=None,
        role=UserRole.ADMIN.value,
        deleted_at=datetime(2026, 6, 2, tzinfo=UTC),
    )
    session = StatementCaptureSession(result_user=result_user)

    updated = await UserAccountRepository().upsert_from_clerk_profile(
        session,
        clerk_id="user_123",
        first_name="Updated",
        last_name="Deleted",
        clerk_profile_updated_at=datetime(2026, 6, 14, tzinfo=UTC),
    )

    assert updated is result_user
    update_sql = _update_clause(session.statements[0])
    assert "first_name = CASE" in update_sql
    assert "last_name = CASE" in update_sql
    assert "deleted_at = " not in update_sql


@pytest.mark.asyncio
async def test_soft_delete_by_clerk_id_sets_deleted_at_once() -> None:
    deleted_at = datetime(2026, 6, 15, tzinfo=UTC)
    user = UserAccount(
        clerk_id="user_123",
        first_name="Test",
        last_name="User",
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
        self.scalar_statements = []

    def add(self, user: UserAccount) -> None:
        self.added.append(user)
        self.user = user

    async def flush(self) -> None:
        self.flushes += 1

    async def scalar(self, statement) -> UserAccount | None:
        self.scalar_statements.append(statement)
        return self.user


class StatementCaptureSession(FakeSession):
    def __init__(
        self,
        *,
        result_user: UserAccount | None,
        user: UserAccount | None = None,
    ) -> None:
        super().__init__(user=result_user if user is None else user)
        self.statements = []
        self._result_user = result_user

    async def execute(self, statement):
        self.statements.append(statement)
        return ScalarResult(self._result_user)


class ScalarResult:
    def __init__(self, value: UserAccount | None) -> None:
        self._value = value

    def scalar_one(self) -> UserAccount:
        if self._value is None:
            raise AssertionError("Expected test result value.")
        return self._value

    def scalar_one_or_none(self) -> UserAccount | None:
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
    sql = _compiled_sql(statement)
    return sql.split(" DO UPDATE SET ", 1)[1].split(" RETURNING ", 1)[0]
