"""Add student daily activity.

Revision ID: 20260613_0013
Revises: 20260610_0012
Create Date: 2026-06-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260613_0013"
down_revision: str | None = "20260610_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "student_daily_activity",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("activity_date", sa.Date(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("login_count", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_account.id"],
            name=op.f("student_daily_activity_user_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("student_daily_activity_pkey")),
        sa.UniqueConstraint(
            "user_id",
            "activity_date",
            name=op.f("student_daily_activity_user_id_activity_date_key"),
        ),
    )
    op.create_index(
        "student_daily_activity_user_id_activity_date_idx",
        "student_daily_activity",
        ["user_id", "activity_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "student_daily_activity_user_id_activity_date_idx",
        table_name="student_daily_activity",
    )
    op.drop_table("student_daily_activity")
