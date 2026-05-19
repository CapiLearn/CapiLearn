"""Add RAG storage schema.

Revision ID: 20260519_0002
Revises: 20260516_0001
Create Date: 2026-05-19

"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "20260519_0002"
down_revision: str | None = "20260516_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class Vector(sa.types.UserDefinedType):
    """Minimal pgvector type for DDL without adding a new dependency yet."""

    cache_ok = True

    def get_col_spec(self, **kw: Any) -> str:
        return "vector"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "rag_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("course_name", sa.String(length=160), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("rag_documents_pkey")),
    )
    op.create_index(
        op.f("rag_documents_content_hash_idx"),
        "rag_documents",
        ["content_hash"],
        unique=False,
    )
    op.create_index(
        op.f("rag_documents_course_name_idx"),
        "rag_documents",
        ["course_name"],
        unique=False,
    )

    op.create_table(
        "rag_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["rag_documents.id"],
            name=op.f("rag_chunks_document_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("rag_chunks_pkey")),
    )
    op.create_index(
        op.f("rag_chunks_document_id_idx"),
        "rag_chunks",
        ["document_id"],
        unique=False,
    )

    op.create_table(
        "rag_embeddings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("embedding", Vector(), nullable=False),
        sa.Column("embedding_model", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["rag_chunks.id"],
            name=op.f("rag_embeddings_chunk_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("rag_embeddings_pkey")),
    )
    op.create_index(
        op.f("rag_embeddings_chunk_id_idx"),
        "rag_embeddings",
        ["chunk_id"],
        unique=False,
    )
    op.create_index(
        op.f("rag_embeddings_embedding_model_idx"),
        "rag_embeddings",
        ["embedding_model"],
        unique=False,
    )

    op.create_table(
        "rag_retrieval_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("retrieved_chunk_ids", sa.JSON(), nullable=False),
        sa.Column("scores", sa.JSON(), nullable=False),
        sa.Column("rag_index_version", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversation.id"],
            name=op.f("rag_retrieval_logs_conversation_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["message.id"],
            name=op.f("rag_retrieval_logs_message_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("rag_retrieval_logs_pkey")),
    )
    op.create_index(
        op.f("rag_retrieval_logs_conversation_id_idx"),
        "rag_retrieval_logs",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        op.f("rag_retrieval_logs_message_id_idx"),
        "rag_retrieval_logs",
        ["message_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("rag_retrieval_logs_message_id_idx"), table_name="rag_retrieval_logs")
    op.drop_index(
        op.f("rag_retrieval_logs_conversation_id_idx"),
        table_name="rag_retrieval_logs",
    )
    op.drop_table("rag_retrieval_logs")
    op.drop_index(op.f("rag_embeddings_embedding_model_idx"), table_name="rag_embeddings")
    op.drop_index(op.f("rag_embeddings_chunk_id_idx"), table_name="rag_embeddings")
    op.drop_table("rag_embeddings")
    op.drop_index(op.f("rag_chunks_document_id_idx"), table_name="rag_chunks")
    op.drop_table("rag_chunks")
    op.drop_index(op.f("rag_documents_course_name_idx"), table_name="rag_documents")
    op.drop_index(op.f("rag_documents_content_hash_idx"), table_name="rag_documents")
    op.drop_table("rag_documents")
