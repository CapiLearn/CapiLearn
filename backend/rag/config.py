from enum import StrEnum
from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.rag.defaults import (
    DEFAULT_RAG_CANDIDATE_POOL_MULTIPLIER,
    DEFAULT_RAG_EMBEDDING_DIMENSIONS,
    DEFAULT_RAG_EMBEDDING_PROVIDER,
    DEFAULT_RAG_MAX_CANDIDATES,
    DEFAULT_RAG_MODEL_NAME,
    DEFAULT_RAG_TOP_K,
    validate_pgvector_embedding_contract,
)


class RagBackend(StrEnum):
    CHROMA = "chroma"
    PGVECTOR = "pgvector"


class RagSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="RAG_", extra="ignore")

    backend: RagBackend = RagBackend.PGVECTOR
    embedding_provider: str = DEFAULT_RAG_EMBEDDING_PROVIDER
    model_name: str = DEFAULT_RAG_MODEL_NAME
    embedding_dimensions: int = DEFAULT_RAG_EMBEDDING_DIMENSIONS
    top_k: int = Field(default=DEFAULT_RAG_TOP_K, ge=1)
    candidate_pool_multiplier: int = Field(
        default=DEFAULT_RAG_CANDIDATE_POOL_MULTIPLIER,
        ge=1,
    )
    max_candidates: int = Field(
        default=DEFAULT_RAG_MAX_CANDIDATES,
        ge=1,
        le=500,
    )
    write_retrieval_logs: bool = True
    index_version: str | None = None

    @model_validator(mode="after")
    def validate_rag_contract(self) -> "RagSettings":
        if self.top_k > self.max_candidates:
            raise ValueError("RAG_TOP_K must be less than or equal to RAG_MAX_CANDIDATES")
        if self.backend == RagBackend.CHROMA:
            raise ValueError("Unsupported RAG backend. Configure RAG_BACKEND=pgvector.")
        if self.backend == RagBackend.PGVECTOR:
            validate_pgvector_embedding_contract(
                embedding_provider=self.embedding_provider,
                model_name=self.model_name,
                embedding_dimensions=self.embedding_dimensions,
            )
        return self


@lru_cache
def get_rag_settings() -> RagSettings:
    return RagSettings()


rag_settings = get_rag_settings()
