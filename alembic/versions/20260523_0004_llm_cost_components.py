"""Add granular LLM cost components.

Revision ID: 20260523_0004
Revises: 20260520_0003
Create Date: 2026-05-23

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260523_0004"
down_revision: str | None = "20260520_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_cost_component",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("user_message_id", sa.Uuid(), nullable=False),
        sa.Column("assistant_message_id", sa.Uuid(), nullable=False),
        sa.Column("component_order", sa.Integer(), nullable=False),
        sa.Column("component_type", sa.String(length=80), nullable=False),
        sa.Column("attempt_index", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=120), nullable=True),
        sa.Column("configured_model", sa.String(length=255), nullable=True),
        sa.Column("response_model", sa.String(length=255), nullable=True),
        sa.Column("finish_reason", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Numeric(18, 12), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_type", sa.String(length=120), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["assistant_message_id"],
            ["message.id"],
            name=op.f("llm_cost_component_assistant_message_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversation.id"],
            name=op.f("llm_cost_component_conversation_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_message_id"],
            ["message.id"],
            name=op.f("llm_cost_component_user_message_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("llm_cost_component_pkey")),
    )
    op.create_index(
        "llm_cost_component_assistant_message_id_idx",
        "llm_cost_component",
        ["assistant_message_id"],
        unique=False,
    )
    op.create_index(
        "llm_cost_component_component_type_created_at_idx",
        "llm_cost_component",
        ["component_type", "created_at"],
        unique=False,
    )
    op.create_index(
        "llm_cost_component_conversation_created_at_idx",
        "llm_cost_component",
        ["conversation_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "llm_cost_component_created_at_idx",
        "llm_cost_component",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("llm_cost_component_user_id_idx"),
        "llm_cost_component",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("llm_cost_component_user_id_idx"), table_name="llm_cost_component")
    op.drop_index("llm_cost_component_created_at_idx", table_name="llm_cost_component")
    op.drop_index(
        "llm_cost_component_conversation_created_at_idx",
        table_name="llm_cost_component",
    )
    op.drop_index(
        "llm_cost_component_component_type_created_at_idx",
        table_name="llm_cost_component",
    )
    op.drop_index(
        "llm_cost_component_assistant_message_id_idx",
        table_name="llm_cost_component",
    )
    op.drop_table("llm_cost_component")
