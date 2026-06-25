"""Add deterministic RAG chunk contract fields.

Revision ID: 20260610_0011
Revises: 20260609_0010
Create Date: 2026-06-10

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260610_0011"
down_revision: str | None = "20260609_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("rag_chunks", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.add_column("rag_chunks", sa.Column("char_start", sa.Integer(), nullable=True))
    op.add_column("rag_chunks", sa.Column("char_end", sa.Integer(), nullable=True))
    op.add_column("rag_chunks", sa.Column("heading_path", sa.JSON(), nullable=True))
    op.add_column("rag_chunks", sa.Column("section_heading", sa.Text(), nullable=True))
    op.add_column("rag_chunks", sa.Column("chunk_type", sa.String(length=40), nullable=True))
    op.add_column("rag_chunks", sa.Column("chunker_version", sa.String(length=120), nullable=True))
    op.create_index(
        op.f("rag_chunks_content_hash_idx"),
        "rag_chunks",
        ["content_hash"],
        unique=False,
    )
    op.create_unique_constraint(
        "rag_chunks_document_id_chunk_index_key",
        "rag_chunks",
        ["document_id", "chunk_index"],
    )
    op.create_unique_constraint(
        "rag_embeddings_chunk_id_embedding_model_key",
        "rag_embeddings",
        ["chunk_id", "embedding_model"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "rag_embeddings_chunk_id_embedding_model_key",
        "rag_embeddings",
        type_="unique",
    )
    op.drop_constraint(
        "rag_chunks_document_id_chunk_index_key",
        "rag_chunks",
        type_="unique",
    )
    op.drop_index(op.f("rag_chunks_content_hash_idx"), table_name="rag_chunks")
    op.drop_column("rag_chunks", "chunker_version")
    op.drop_column("rag_chunks", "chunk_type")
    op.drop_column("rag_chunks", "section_heading")
    op.drop_column("rag_chunks", "heading_path")
    op.drop_column("rag_chunks", "char_end")
    op.drop_column("rag_chunks", "char_start")
    op.drop_column("rag_chunks", "content_hash")
