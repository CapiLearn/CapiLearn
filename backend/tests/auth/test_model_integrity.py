from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from backend.auth.models import UserAccount


def test_user_account_role_constraint_renders_expected_name() -> None:
    ddl = str(CreateTable(UserAccount.__table__).compile(dialect=postgresql.dialect()))

    assert "CONSTRAINT user_account_role_check CHECK" in ddl
    assert "user_account_user_account_role_check_check" not in ddl


def test_user_account_maps_clerk_profile_projection_fields() -> None:
    assert "username" not in UserAccount.__table__.columns
    assert "email" in UserAccount.__table__.columns
    assert "display_name" in UserAccount.__table__.columns
    assert "profile_refreshed_at" not in UserAccount.__table__.columns
    assert "profile_synced_at" in UserAccount.__table__.columns
    assert "clerk_profile_updated_at" in UserAccount.__table__.columns
    assert UserAccount.__table__.columns["display_name"].nullable is False
    assert UserAccount.__table__.columns["email"].nullable is True
    assert UserAccount.__table__.columns["profile_synced_at"].nullable is False
    assert UserAccount.__table__.columns["clerk_profile_updated_at"].nullable is True


def test_user_account_does_not_index_profile_projection_fields() -> None:
    indexes = {index.name: index for index in UserAccount.__table__.indexes}

    assert "user_account_username_idx" not in indexes
    assert "user_account_email_idx" not in indexes
