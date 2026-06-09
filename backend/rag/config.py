from enum import StrEnum
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.rag.defaults import DEFAULT_RAG_MODEL_NAME, DEFAULT_RAG_TOP_K


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


@lru_cache
def get_rag_settings() -> RagSettings:
    return RagSettings()


rag_settings = get_rag_settings()
