"""Drop persisted Clerk profile fields.

Revision ID: 20260606_0007
Revises: 20260606_0006
Create Date: 2026-06-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260606_0007"
down_revision: str | None = "20260606_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("user_account", "display_name")
    op.drop_column("user_account", "email")


def downgrade() -> None:
    op.add_column(
        "user_account",
        sa.Column("email", sa.String(length=320), nullable=True),
    )
    op.add_column(
        "user_account",
        sa.Column("display_name", sa.String(length=255), nullable=True),
    )
