"""Set RAG embedding dimensions and add cosine index.

Revision ID: 20260606_0005
Revises: 20260606_0004
Create Date: 2026-06-06

"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260606_0005"
down_revision: str | None = "20260606_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE rag_embeddings
        ALTER COLUMN embedding TYPE vector(384)
        USING embedding::vector(384)
        """
    )
    op.create_index(
        "rag_embeddings_embedding_cosine_idx",
        "rag_embeddings",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index(
        "rag_embeddings_embedding_cosine_idx",
        table_name="rag_embeddings",
        postgresql_using="hnsw",
    )
    op.execute(
        """
        ALTER TABLE rag_embeddings
        ALTER COLUMN embedding TYPE vector
        USING embedding::vector
        """
    )
