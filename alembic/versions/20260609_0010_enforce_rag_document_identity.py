"""Enforce RAG document source identity.

Revision ID: 20260609_0010
Revises: 20260606_0009
Create Date: 2026-06-09

"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260609_0010"
down_revision: str | None = "20260606_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "rag_documents_source_type_source_path_key",
        "rag_documents",
        ["source_type", "source_path"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "rag_documents_source_type_source_path_key",
        "rag_documents",
        type_="unique",
    )
