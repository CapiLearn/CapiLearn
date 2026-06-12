from collections.abc import Callable
from functools import lru_cache
from threading import Lock
from typing import Any, Protocol

from sentence_transformers import SentenceTransformer


class QueryEmbeddingProvider(Protocol):
    def embed_query(self, query_text: str, *, model_name: str) -> list[float]: ...


class SentenceTransformerEmbeddingProvider:
    def __init__(
        self,
        *,
        model_factory: Callable[[str], Any] = SentenceTransformer,
    ) -> None:
        self._model_factory = model_factory
        self._models: dict[str, Any] = {}
        self._model_lock = Lock()

    def embed_query(self, query_text: str, *, model_name: str) -> list[float]:
        model = self._get_model(model_name)
        embedding = model.encode(query_text)
        return embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)

    def _get_model(self, model_name: str) -> Any:
        if model_name not in self._models:
            with self._model_lock:
                if model_name not in self._models:
                    self._models[model_name] = self._model_factory(model_name)
        return self._models[model_name]


@lru_cache(maxsize=1)
def get_embedding_provider() -> QueryEmbeddingProvider:
    return SentenceTransformerEmbeddingProvider()
