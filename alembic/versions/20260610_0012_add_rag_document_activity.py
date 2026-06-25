"""Add RAG document activity fields.

Revision ID: 20260610_0012
Revises: 20260610_0011
Create Date: 2026-06-10

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260610_0012"
down_revision: str | None = "20260610_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rag_documents",
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column(
        "rag_documents",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("rag_documents_is_active_idx"),
        "rag_documents",
        ["is_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("rag_documents_is_active_idx"), table_name="rag_documents")
    op.drop_column("rag_documents", "deleted_at")
    op.drop_column("rag_documents", "is_active")
