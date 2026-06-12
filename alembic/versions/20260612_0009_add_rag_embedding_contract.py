"""Add the full RAG embedding identity contract.

Revision ID: 20260612_0009
Revises: 20260610_0008
Create Date: 2026-06-12

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260612_0009"
down_revision: str | None = "20260610_0008"
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
        SET embedding_provider = CASE
            WHEN embedding_model LIKE 'text-embedding-%'
                OR embedding_model = 'openai/ada-002'
                OR embedding_model = 'text-embedding-ada-002'
                THEN 'openai'
            WHEN embedding_model LIKE 'sentence-transformers/%'
                OR embedding_model LIKE 'all-MiniLM-%'
                THEN 'sentence_transformers'
            ELSE 'legacy_unknown'
        END,
        embedding_dimensions = 384
        """
    )
    op.alter_column("rag_embeddings", "embedding_provider", nullable=False)
    op.alter_column("rag_embeddings", "embedding_dimensions", nullable=False)
    op.create_index(
        op.f("rag_embeddings_embedding_provider_idx"),
        "rag_embeddings",
        ["embedding_provider"],
        unique=False,
    )
    op.drop_constraint(
        "rag_embeddings_chunk_id_embedding_model_key",
        "rag_embeddings",
        type_="unique",
    )
    op.create_unique_constraint(
        "rag_embeddings_chunk_id_embedding_contract_key",
        "rag_embeddings",
        [
            "chunk_id",
            "embedding_provider",
            "embedding_model",
            "embedding_dimensions",
        ],
    )


def downgrade() -> None:
    op.drop_constraint(
        "rag_embeddings_chunk_id_embedding_contract_key",
        "rag_embeddings",
        type_="unique",
    )
    op.execute(
        """
        DELETE FROM rag_embeddings
        WHERE id IN (
            SELECT id
            FROM (
                SELECT
                    id,
                    row_number() OVER (
                        PARTITION BY chunk_id, embedding_model
                        ORDER BY created_at, id
                    ) AS contract_rank
                FROM rag_embeddings
            ) ranked_embeddings
            WHERE contract_rank > 1
        )
        """
    )
    op.create_unique_constraint(
        "rag_embeddings_chunk_id_embedding_model_key",
        "rag_embeddings",
        ["chunk_id", "embedding_model"],
    )
    op.drop_index(
        op.f("rag_embeddings_embedding_provider_idx"),
        table_name="rag_embeddings",
    )
    op.drop_column("rag_embeddings", "embedding_dimensions")
    op.drop_column("rag_embeddings", "embedding_provider")
