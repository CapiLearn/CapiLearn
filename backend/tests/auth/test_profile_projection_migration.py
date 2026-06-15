from pathlib import Path
from runpy import run_path

import pytest

MIGRATION = run_path(
    str(
        Path(__file__).parents[3]
        / "alembic"
        / "versions"
        / "20260615_0014_restore_user_profile_projection.py"
    )
)


def test_restore_profile_projection_migration_allows_empty_user_account() -> None:
    MIGRATION["_assert_user_account_empty"](FakeConnection(has_users=False))


def test_restore_profile_projection_migration_rejects_existing_users() -> None:
    with pytest.raises(RuntimeError, match="user_account must be empty"):
        MIGRATION["_assert_user_account_empty"](FakeConnection(has_users=True))


class FakeConnection:
    def __init__(self, *, has_users: bool) -> None:
        self.has_users = has_users

    def execute(self, statement):
        assert "SELECT EXISTS (SELECT 1 FROM user_account)" in str(statement)
        return FakeResult(self.has_users)


class FakeResult:
    def __init__(self, value: bool) -> None:
        self._value = value

    def scalar_one(self) -> bool:
        return self._value
