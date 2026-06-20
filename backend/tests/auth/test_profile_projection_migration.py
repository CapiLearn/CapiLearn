from runpy import run_path

import pytest

MIGRATION = run_path("alembic/versions/20260615_0014_restore_user_profile_projection.py")


def test_restore_profile_projection_migration_allows_empty_user_account() -> None:
    MIGRATION["_assert_user_account_empty"](FakeConnection(has_users=False))


def test_restore_profile_projection_migration_rejects_existing_users() -> None:
    with pytest.raises(RuntimeError, match="user_account must be empty"):
        MIGRATION["_assert_user_account_empty"](FakeConnection(has_users=True))


def test_restore_profile_projection_migration_upgrade_emits_name_projection_ops() -> None:
    recorder = MigrationOperationRecorder()

    _set_migration_op(recorder)
    MIGRATION["upgrade"]()

    assert recorder.added_columns == [
        ("user_account", "first_name", False),
        ("user_account", "last_name", False),
        ("user_account", "clerk_profile_updated_at", True),
    ]
    assert recorder.created_constraints == [
        (
            "user_account_first_name_not_blank_check",
            "user_account",
            "length(trim(first_name)) > 0",
        ),
        (
            "user_account_last_name_not_blank_check",
            "user_account",
            "length(trim(last_name)) > 0",
        ),
    ]
    emitted_column_names = {column_name for _, column_name, _ in recorder.added_columns}
    assert emitted_column_names.isdisjoint({"display_name", "email", "profile_synced_at"})


def test_restore_profile_projection_migration_downgrade_drops_name_projection_ops() -> None:
    recorder = MigrationOperationRecorder()

    _set_migration_op(recorder)
    MIGRATION["downgrade"]()

    assert recorder.dropped_constraints == [
        ("user_account_last_name_not_blank_check", "user_account", "check"),
        ("user_account_first_name_not_blank_check", "user_account", "check"),
    ]
    assert recorder.dropped_columns == [
        ("user_account", "clerk_profile_updated_at"),
        ("user_account", "last_name"),
        ("user_account", "first_name"),
    ]


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


def _set_migration_op(recorder: "MigrationOperationRecorder") -> None:
    MIGRATION["upgrade"].__globals__["op"] = recorder
    MIGRATION["downgrade"].__globals__["op"] = recorder


class MigrationOperationRecorder:
    def __init__(self) -> None:
        self.added_columns: list[tuple[str, str, bool]] = []
        self.created_constraints: list[tuple[str, str, str]] = []
        self.dropped_constraints: list[tuple[str, str, str]] = []
        self.dropped_columns: list[tuple[str, str]] = []

    def get_bind(self) -> FakeConnection:
        return FakeConnection(has_users=False)

    def f(self, name: str) -> str:
        return name

    def add_column(self, table_name: str, column) -> None:
        self.added_columns.append((table_name, column.name, column.nullable))

    def create_check_constraint(self, name: str, table_name: str, condition: str) -> None:
        self.created_constraints.append((name, table_name, condition))

    def drop_constraint(self, name: str, table_name: str, *, type_: str) -> None:
        self.dropped_constraints.append((name, table_name, type_))

    def drop_column(self, table_name: str, column_name: str) -> None:
        self.dropped_columns.append((table_name, column_name))
