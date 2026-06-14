"""Add student daily activity.

Revision ID: 20260613_0013
Revises: 20260612_0009
Create Date: 2026-06-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260613_0013"
down_revision: str | None = "20260612_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _ensure_user_account_schema()
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


def _ensure_user_account_schema() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_account (
            id UUID NOT NULL,
            clerk_id VARCHAR(255) NOT NULL,
            role VARCHAR(32) DEFAULT 'student' NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            deleted_at TIMESTAMP WITH TIME ZONE,
            CONSTRAINT user_account_pkey PRIMARY KEY (id),
            CONSTRAINT user_account_role_check
                CHECK (role IN ('student', 'instructor', 'admin'))
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS user_account_clerk_id_idx ON user_account (clerk_id)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS user_account_role_idx ON user_account (role)")
    op.execute(
        """
        INSERT INTO user_account (
            id,
            clerk_id,
            role,
            created_at,
            updated_at,
            deleted_at
        )
        SELECT
            user_id,
            'legacy:migrated-user:' || user_id::text,
            'student',
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP,
            NULL
        FROM (
            SELECT DISTINCT user_id FROM conversation
            UNION
            SELECT DISTINCT user_id FROM message
            UNION
            SELECT DISTINCT user_id FROM llm_cost_component
        ) legacy_user
        ON CONFLICT (id) DO NOTHING
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'conversation_user_id_fkey'
                    AND conrelid = 'conversation'::regclass
            ) THEN
                ALTER TABLE conversation
                ADD CONSTRAINT conversation_user_id_fkey
                FOREIGN KEY (user_id) REFERENCES user_account(id);
            END IF;

            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'message_user_id_fkey'
                    AND conrelid = 'message'::regclass
            ) THEN
                ALTER TABLE message
                ADD CONSTRAINT message_user_id_fkey
                FOREIGN KEY (user_id) REFERENCES user_account(id);
            END IF;

            IF to_regclass('llm_cost_component') IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'llm_cost_component_user_id_fkey'
                        AND conrelid = 'llm_cost_component'::regclass
                ) THEN
                ALTER TABLE llm_cost_component
                ADD CONSTRAINT llm_cost_component_user_id_fkey
                FOREIGN KEY (user_id) REFERENCES user_account(id);
            END IF;
        END
        $$;
        """
    )
