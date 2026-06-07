from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from backend.auth.models import UserAccount


def test_user_account_role_constraint_renders_expected_name() -> None:
    ddl = str(CreateTable(UserAccount.__table__).compile(dialect=postgresql.dialect()))

    assert "CONSTRAINT user_account_role_check CHECK" in ddl
    assert "user_account_user_account_role_check_check" not in ddl


def test_user_account_does_not_map_clerk_profile_fields() -> None:
    assert "email" not in UserAccount.__table__.columns
    assert "display_name" not in UserAccount.__table__.columns
