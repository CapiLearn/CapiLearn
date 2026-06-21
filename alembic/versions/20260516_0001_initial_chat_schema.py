"""Initial chat schema.

Revision ID: 20260516_0001
Revises:
Create Date: 2026-05-16

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260516_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("model_profile_key", sa.String(length=120), nullable=False),
        sa.Column("model_profile_version", sa.String(length=120), nullable=True),
        sa.Column("guardrails_config_id", sa.String(length=120), nullable=True),
        sa.Column("rag_index_version", sa.String(length=120), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("conversation_pkey")),
    )
    op.create_index(
        op.f("conversation_status_idx"),
        "conversation",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("conversation_user_id_idx"),
        "conversation",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "message",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("content_parts", sa.JSON(), nullable=True),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("finish_reason", sa.String(length=120), nullable=True),
        sa.Column("retrieved_context", sa.JSON(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("input_guardrail_result", sa.JSON(), nullable=True),
        sa.Column("output_guardrail_result", sa.JSON(), nullable=True),
        sa.Column("blocked_reason", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("provider_response", sa.JSON(), nullable=True),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversation.id"],
            name=op.f("message_conversation_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("message_pkey")),
        sa.UniqueConstraint(
            "conversation_id",
            "sequence",
            name="message_conversation_sequence_key",
        ),
    )
    op.create_index(
        op.f("message_conversation_id_idx"),
        "message",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(op.f("message_user_id_idx"), "message", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("message_user_id_idx"), table_name="message")
    op.drop_index(op.f("message_conversation_id_idx"), table_name="message")
    op.drop_table("message")
    op.drop_index(op.f("conversation_user_id_idx"), table_name="conversation")
    op.drop_index(op.f("conversation_status_idx"), table_name="conversation")
    op.drop_table("conversation")
