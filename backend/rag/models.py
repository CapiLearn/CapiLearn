from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base
from backend.rag.defaults import DEFAULT_RAG_EMBEDDING_DIMENSIONS, DEFAULT_RAG_EMBEDDING_PROVIDER

EMBEDDING_DIMENSIONS = DEFAULT_RAG_EMBEDDING_DIMENSIONS


def utc_now() -> datetime:
    return datetime.now(UTC)


class RagDocument(Base):
    __tablename__ = "rag_documents"
    __table_args__ = (
        UniqueConstraint(
            "source_type",
            "source_path",
            name="rag_documents_source_type_source_path_key",
        ),
        Index("rag_documents_is_active_idx", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    course_name: Mapped[str | None] = mapped_column(String(160), index=True)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extra_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    chunks: Mapped[list["RagChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )


class RagChunk(Base):
    __tablename__ = "rag_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "chunk_index",
            name="rag_chunks_document_id_chunk_index_key",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("rag_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    char_start: Mapped[int | None] = mapped_column(Integer)
    char_end: Mapped[int | None] = mapped_column(Integer)
    heading_path: Mapped[list[str] | None] = mapped_column(JSON)
    section_heading: Mapped[str | None] = mapped_column(Text)
    chunk_type: Mapped[str | None] = mapped_column(String(40))
    chunker_version: Mapped[str | None] = mapped_column(String(120))
    extra_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    document: Mapped[RagDocument] = relationship(back_populates="chunks")
    embeddings: Mapped[list["RagEmbedding"]] = relationship(
        back_populates="chunk",
        cascade="all, delete-orphan",
    )


class RagEmbedding(Base):
    __tablename__ = "rag_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "chunk_id",
            "embedding_provider",
            "embedding_model",
            "embedding_dimensions",
            name="rag_embeddings_chunk_id_embedding_contract_key",
        ),
        Index("rag_embeddings_embedding_provider_idx", "embedding_provider"),
        Index(
            "rag_embeddings_embedding_cosine_idx",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    chunk_id: Mapped[UUID] = mapped_column(
        ForeignKey("rag_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    embedding: Mapped[Any] = mapped_column(VECTOR(EMBEDDING_DIMENSIONS), nullable=False)
    embedding_provider: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default=DEFAULT_RAG_EMBEDDING_PROVIDER,
    )
    embedding_model: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    embedding_dimensions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=EMBEDDING_DIMENSIONS,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    chunk: Mapped[RagChunk] = relationship(back_populates="embeddings")


class RagRetrievalLog(Base):
    __tablename__ = "rag_retrieval_logs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("conversation.id", ondelete="SET NULL"),
        index=True,
    )
    message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("message.id", ondelete="SET NULL"),
        index=True,
    )
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_chunk_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    scores: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    rag_index_version: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
