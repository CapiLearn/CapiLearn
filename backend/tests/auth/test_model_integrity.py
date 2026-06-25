from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from backend.auth.models import UserAccount


def test_user_account_role_constraint_renders_expected_name() -> None:
    ddl = str(CreateTable(UserAccount.__table__).compile(dialect=postgresql.dialect()))

    assert "CONSTRAINT user_account_role_check CHECK" in ddl
    assert "user_account_user_account_role_check_check" not in ddl


def test_user_account_name_constraints_render_expected_names() -> None:
    ddl = str(CreateTable(UserAccount.__table__).compile(dialect=postgresql.dialect()))

    assert "CONSTRAINT user_account_first_name_not_blank_check CHECK" in ddl
    assert "CONSTRAINT user_account_last_name_not_blank_check CHECK" in ddl


def test_user_account_maps_clerk_profile_projection_fields() -> None:
    assert "username" not in UserAccount.__table__.columns
    assert "email" not in UserAccount.__table__.columns
    assert "display_name" not in UserAccount.__table__.columns
    assert "profile_refreshed_at" not in UserAccount.__table__.columns
    assert "profile_synced_at" not in UserAccount.__table__.columns
    assert "first_name" in UserAccount.__table__.columns
    assert "last_name" in UserAccount.__table__.columns
    assert "clerk_profile_updated_at" in UserAccount.__table__.columns
    assert UserAccount.__table__.columns["first_name"].nullable is False
    assert UserAccount.__table__.columns["last_name"].nullable is False
    assert UserAccount.__table__.columns["clerk_profile_updated_at"].nullable is True


def test_user_account_does_not_index_profile_projection_fields() -> None:
    indexes = {index.name: index for index in UserAccount.__table__.indexes}

    assert "user_account_username_idx" not in indexes
    assert "user_account_email_idx" not in indexes
