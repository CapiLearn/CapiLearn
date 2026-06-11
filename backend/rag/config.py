from enum import StrEnum
from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.rag.defaults import (
    DEFAULT_RAG_EMBEDDING_DIMENSIONS,
    DEFAULT_RAG_EMBEDDING_PROVIDER,
    DEFAULT_RAG_MODEL_NAME,
    DEFAULT_RAG_TOP_K,
    validate_pgvector_dimensions,
)


class RagBackend(StrEnum):
    CHROMA = "chroma"
    PGVECTOR = "pgvector"


class RagEmbeddingProvider(StrEnum):
    OPENAI = "openai"
    SENTENCE_TRANSFORMERS = "sentence_transformers"


class RagSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="RAG_", extra="ignore")

    backend: RagBackend = RagBackend.PGVECTOR
    embedding_provider: RagEmbeddingProvider = RagEmbeddingProvider(DEFAULT_RAG_EMBEDDING_PROVIDER)
    model_name: str = DEFAULT_RAG_MODEL_NAME
    embedding_dimensions: int = Field(default=DEFAULT_RAG_EMBEDDING_DIMENSIONS, ge=1)
    top_k: int = Field(default=DEFAULT_RAG_TOP_K, ge=1)
    write_retrieval_logs: bool = True
    index_version: str | None = None
    openai_api_key: str | None = Field(
        default=None,
        validation_alias="OPENAI_API_KEY",
        repr=False,
    )

    @field_validator("backend", mode="before")
    @classmethod
    def reject_legacy_chroma_backend(cls, value: object) -> object:
        if value == RagBackend.CHROMA or value == RagBackend.CHROMA.value:
            raise ValueError(
                "Chroma is no longer a supported runtime RAG backend. "
                "Use RAG_BACKEND=pgvector. The legacy Chroma path was disabled "
                "because it can query MiniLM-built vector stores with non-MiniLM "
                "embedding providers."
            )
        return value

    @model_validator(mode="after")
    def validate_embedding_contract(self) -> "RagSettings":
        validate_embedding_contract(
            provider=self.embedding_provider,
            model_name=self.model_name,
            dimensions=self.embedding_dimensions,
            openai_api_key=self.openai_api_key,
        )
        return self


def validate_embedding_contract(
    *,
    provider: RagEmbeddingProvider,
    model_name: str,
    dimensions: int,
    openai_api_key: str | None,
) -> None:
    validate_pgvector_dimensions(dimensions)
    if provider == RagEmbeddingProvider.OPENAI:
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when RAG_EMBEDDING_PROVIDER='openai'.")
        if model_name != "text-embedding-3-small":
            raise ValueError(
                "RAG_MODEL_NAME must be 'text-embedding-3-small' when "
                "RAG_EMBEDDING_PROVIDER='openai'."
            )
        return
    if provider == RagEmbeddingProvider.SENTENCE_TRANSFORMERS:
        if model_name != DEFAULT_RAG_MODEL_NAME:
            raise ValueError(
                f"RAG_MODEL_NAME must be {DEFAULT_RAG_MODEL_NAME!r} when "
                "RAG_EMBEDDING_PROVIDER='sentence_transformers'."
            )
        return
    raise ValueError(f"Unsupported RAG embedding provider: {provider!r}")


@lru_cache
def get_rag_settings() -> RagSettings:
    return RagSettings()


rag_settings = get_rag_settings()
