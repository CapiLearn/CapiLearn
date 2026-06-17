import os
from functools import lru_cache
from typing import Any, Protocol

from litellm import embedding as litellm_embedding

from backend.rag.defaults import (
    DEFAULT_RAG_EMBEDDING_DIMENSIONS,
    DEFAULT_RAG_EMBEDDING_PROVIDER,
    DEFAULT_RAG_MODEL_NAME,
    validate_pgvector_embedding_contract,
)


class QueryEmbeddingProvider(Protocol):
    def embed_query(self, query_text: str, *, model_name: str) -> list[float]: ...

    def embed_documents(
        self,
        texts: list[str],
        *,
        model_name: str,
        embedding_dimensions: int,
    ) -> list[list[float]]: ...


class OpenAIEmbeddingProvider:
    def __init__(
        self,
        *,
        embedding_provider: str = DEFAULT_RAG_EMBEDDING_PROVIDER,
        embedding_dimensions: int = DEFAULT_RAG_EMBEDDING_DIMENSIONS,
        embedding_client: Any = litellm_embedding,
        api_key: str | None = None,
    ) -> None:
        validate_pgvector_embedding_contract(
            embedding_provider=embedding_provider,
            model_name=DEFAULT_RAG_MODEL_NAME,
            embedding_dimensions=embedding_dimensions,
        )
        if api_key is None and not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY is required for OpenAI RAG embeddings.")
        self._embedding_dimensions = embedding_dimensions
        self._embedding_client = embedding_client

    def embed_query(self, query_text: str, *, model_name: str) -> list[float]:
        return self.embed_documents(
            [query_text],
            model_name=model_name,
            embedding_dimensions=self._embedding_dimensions,
        )[0]

    def embed_documents(
        self,
        texts: list[str],
        *,
        model_name: str,
        embedding_dimensions: int,
    ) -> list[list[float]]:
        validate_pgvector_embedding_contract(
            embedding_provider=DEFAULT_RAG_EMBEDDING_PROVIDER,
            model_name=model_name,
            embedding_dimensions=embedding_dimensions,
        )
        response = self._embedding_client(
            model=model_name,
            input=texts,
            dimensions=embedding_dimensions,
        )
        vectors = [_embedding_to_vector(_embedding_value(item)) for item in response.data]
        if len(vectors) != len(texts):
            raise ValueError(
                "Embedding provider returned a different number of vectors than texts."
            )
        return vectors


def _embedding_to_vector(value: Any) -> list[float]:
    return value.tolist() if hasattr(value, "tolist") else list(value)


def _embedding_value(item: Any) -> Any:
    if isinstance(item, dict):
        return item["embedding"]
    return item.embedding


@lru_cache(maxsize=1)
def get_embedding_provider() -> QueryEmbeddingProvider:
    return OpenAIEmbeddingProvider()
