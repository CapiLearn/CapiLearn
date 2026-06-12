"""Add local user accounts.

Revision ID: 20260606_0004
Revises: 20260523_0003
Create Date: 2026-06-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260606_0004"
down_revision: str | None = "20260523_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_account",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clerk_id", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=32), server_default="student", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("user_account_pkey")),
    )
    op.create_index(
        "user_account_clerk_id_idx",
        "user_account",
        ["clerk_id"],
        unique=True,
    )
    op.create_index("user_account_role_idx", "user_account", ["role"], unique=False)


def downgrade() -> None:
    op.drop_index("user_account_role_idx", table_name="user_account")
    op.drop_index("user_account_clerk_id_idx", table_name="user_account")
    op.drop_table("user_account")
