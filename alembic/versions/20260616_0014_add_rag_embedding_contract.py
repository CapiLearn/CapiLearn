"""Add full RAG embedding contract.

Revision ID: 20260616_0014
Revises: 20260613_0013
Create Date: 2026-06-16

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260616_0014"
down_revision: str | None = "20260613_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rag_embeddings",
        sa.Column("embedding_provider", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "rag_embeddings",
        sa.Column("embedding_dimensions", sa.Integer(), nullable=True),
    )
    op.execute(
        """
        UPDATE rag_embeddings
        SET
            embedding_provider = 'legacy_unknown',
            embedding_dimensions = 384
        WHERE embedding_provider IS NULL
            OR embedding_dimensions IS NULL
        """
    )
    op.alter_column("rag_embeddings", "embedding_provider", nullable=False)
    op.alter_column("rag_embeddings", "embedding_dimensions", nullable=False)
    op.drop_constraint(
        "rag_embeddings_chunk_id_embedding_model_key",
        "rag_embeddings",
        type_="unique",
    )
    op.create_unique_constraint(
        "rag_embeddings_chunk_id_embedding_contract_key",
        "rag_embeddings",
        ["chunk_id", "embedding_provider", "embedding_model", "embedding_dimensions"],
    )
    op.create_index(
        "rag_embeddings_embedding_provider_idx",
        "rag_embeddings",
        ["embedding_provider"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "rag_embeddings_embedding_provider_idx",
        table_name="rag_embeddings",
    )
    op.drop_constraint(
        "rag_embeddings_chunk_id_embedding_contract_key",
        "rag_embeddings",
        type_="unique",
    )
    op.execute(
        """
        DELETE FROM rag_embeddings kept
        USING rag_embeddings duplicate
        WHERE kept.chunk_id = duplicate.chunk_id
            AND kept.embedding_model = duplicate.embedding_model
            AND kept.ctid > duplicate.ctid
        """
    )
    op.create_unique_constraint(
        "rag_embeddings_chunk_id_embedding_model_key",
        "rag_embeddings",
        ["chunk_id", "embedding_model"],
    )
    op.drop_column("rag_embeddings", "embedding_dimensions")
    op.drop_column("rag_embeddings", "embedding_provider")
