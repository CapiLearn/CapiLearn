"""Restore local user profile projection fields.

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
        sa.Column("display_name", sa.String(length=255), nullable=False),
    )
    op.add_column("user_account", sa.Column("email", sa.String(length=320), nullable=True))
    op.add_column(
        "user_account",
        sa.Column("profile_synced_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column(
        "user_account",
        sa.Column("clerk_profile_updated_at", sa.DateTime(timezone=True), nullable=True),
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
    op.drop_column("user_account", "clerk_profile_updated_at")
    op.drop_column("user_account", "profile_synced_at")
    op.drop_column("user_account", "email")
    op.drop_column("user_account", "display_name")
