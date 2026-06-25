"""Add message history context for citation-aware chat.

Revision ID: 20260624_0016
Revises: 20260617_0015
Create Date: 2026-06-24

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260624_0016"
down_revision: str | None = "20260617_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "message",
        sa.Column("history_context", sa.JSON(), nullable=True),
        if_not_exists=True,
    )
    op.execute(
        sa.text(
            """
            UPDATE message
            SET history_context = '[]'
            WHERE history_context IS NULL
            """
        )
    )
    op.alter_column(
        "message",
        "history_context",
        existing_type=sa.JSON(),
        nullable=False,
    )
    op.add_column(
        "message",
        sa.Column("citations", sa.JSON(), nullable=True),
        if_not_exists=True,
    )
    op.execute(
        sa.text(
            """
            UPDATE message
            SET citations = '[]'
            WHERE citations IS NULL
            """
        )
    )
    op.alter_column(
        "message",
        "citations",
        existing_type=sa.JSON(),
        nullable=False,
    )

    op.drop_column("message", "provider_response", if_exists=True)
    op.drop_column("message", "output_guardrail_result", if_exists=True)
    op.drop_column("message", "input_guardrail_result", if_exists=True)
    op.drop_column("message", "retrieved_context", if_exists=True)
    op.drop_column("message", "finish_reason", if_exists=True)
    op.drop_column("message", "provider_message_id", if_exists=True)
    op.drop_column("message", "content_parts", if_exists=True)
    op.drop_column("message", "metadata", if_exists=True)
    op.drop_column("conversation", "metadata", if_exists=True)


def downgrade() -> None:
    op.add_column(
        "conversation",
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.alter_column("conversation", "metadata", server_default=None)

    op.add_column(
        "message",
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "message",
        sa.Column("content_parts", sa.JSON(), nullable=True),
    )
    op.add_column(
        "message",
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "message",
        sa.Column("finish_reason", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "message",
        sa.Column(
            "retrieved_context",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "message",
        sa.Column("input_guardrail_result", sa.JSON(), nullable=True),
    )
    op.add_column(
        "message",
        sa.Column("output_guardrail_result", sa.JSON(), nullable=True),
    )
    op.add_column(
        "message",
        sa.Column("provider_response", sa.JSON(), nullable=True),
    )
    op.alter_column("message", "retrieved_context", server_default=None)
    op.alter_column("message", "metadata", server_default=None)
    op.drop_column("message", "history_context", if_exists=True)
