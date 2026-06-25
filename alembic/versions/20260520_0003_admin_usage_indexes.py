"""Add admin usage dashboard indexes.

Revision ID: 20260520_0003
Revises: 20260519_0002
Create Date: 2026-05-20

"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260520_0003"
down_revision: str | None = "20260519_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("message_created_at_idx", "message", ["created_at"], unique=False)
    op.create_index(
        "message_role_created_at_idx",
        "message",
        ["role", "created_at"],
        unique=False,
    )
    op.create_index(
        "message_status_created_at_idx",
        "message",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index("conversation_created_at_idx", "conversation", ["created_at"], unique=False)
    op.create_index("conversation_updated_at_idx", "conversation", ["updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("conversation_updated_at_idx", table_name="conversation")
    op.drop_index("conversation_created_at_idx", table_name="conversation")
    op.drop_index("message_status_created_at_idx", table_name="message")
    op.drop_index("message_role_created_at_idx", table_name="message")
    op.drop_index("message_created_at_idx", table_name="message")
