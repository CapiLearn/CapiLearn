"""Restore Clerk-owned user name projection fields.

Revision ID: 20260615_0014
Revises: 20260613_0013
Create Date: 2026-06-15

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260615_0014"
down_revision: str | None = "20260613_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _assert_user_account_empty(op.get_bind())

    op.add_column(
        "user_account",
        sa.Column("first_name", sa.String(length=255), nullable=False),
    )
    op.add_column(
        "user_account",
        sa.Column("last_name", sa.String(length=255), nullable=False),
    )
    op.add_column(
        "user_account",
        sa.Column("clerk_profile_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        op.f("user_account_first_name_not_blank_check"),
        "user_account",
        "length(trim(first_name)) > 0",
    )
    op.create_check_constraint(
        op.f("user_account_last_name_not_blank_check"),
        "user_account",
        "length(trim(last_name)) > 0",
    )


def _assert_user_account_empty(connection: sa.Connection) -> None:
    has_users = connection.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM user_account)")
    ).scalar_one()
    if has_users:
        raise RuntimeError(
            "Cannot restore user profile projection columns: user_account must be empty."
        )


def downgrade() -> None:
    op.drop_constraint(
        op.f("user_account_last_name_not_blank_check"),
        "user_account",
        type_="check",
    )
    op.drop_constraint(
        op.f("user_account_first_name_not_blank_check"),
        "user_account",
        type_="check",
    )
    op.drop_column("user_account", "clerk_profile_updated_at")
    op.drop_column("user_account", "last_name")
    op.drop_column("user_account", "first_name")
