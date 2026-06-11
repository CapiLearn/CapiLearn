from enum import StrEnum
from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.rag.defaults import (
    DEFAULT_RAG_MODEL_NAME,
    DEFAULT_RAG_TOP_K,
    validate_pgvector_model_name,
)


class RagBackend(StrEnum):
    CHROMA = "chroma"
    PGVECTOR = "pgvector"


class RagSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="RAG_", extra="ignore")

    backend: RagBackend = RagBackend.CHROMA
    model_name: str = DEFAULT_RAG_MODEL_NAME
    top_k: int = Field(default=DEFAULT_RAG_TOP_K, ge=1)
    write_retrieval_logs: bool = True
    index_version: str | None = None

    @model_validator(mode="after")
    def validate_pgvector_model_contract(self) -> "RagSettings":
        if self.backend == RagBackend.PGVECTOR:
            validate_pgvector_model_name(self.model_name)
        return self


@lru_cache
def get_rag_settings() -> RagSettings:
    return RagSettings()


rag_settings = get_rag_settings()
