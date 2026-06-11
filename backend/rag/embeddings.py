from __future__ import annotations

from collections.abc import Callable, Sequence
from importlib import import_module
from threading import Lock
from typing import Any, Protocol

from openai import OpenAI

from backend.rag.config import RagEmbeddingProvider, RagSettings


class EmbeddingProvider(Protocol):
    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    def embed_text(self, text: str) -> list[float]: ...

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]: ...


class OpenAIEmbeddingProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model_name: str,
        dimensions: int,
        client: Any | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI embeddings.")
        self._model_name = model_name
        self._dimensions = dimensions
        self._client = client or OpenAI(api_key=api_key, timeout=30.0, max_retries=2)

    @property
    def provider_name(self) -> str:
        return RagEmbeddingProvider.OPENAI.value

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._client.embeddings.create(
            model=self._model_name,
            input=list(texts),
            dimensions=self._dimensions,
            encoding_format="float",
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        if len(ordered) != len(texts):
            raise ValueError(
                "OpenAI embeddings response count did not match the requested text count."
            )
        vectors = [list(item.embedding) for item in ordered]
        _validate_vectors(vectors, dimensions=self._dimensions, provider_name=self.provider_name)
        return vectors


class SentenceTransformerEmbeddingProvider:
    def __init__(
        self,
        *,
        model_name: str,
        dimensions: int,
        model_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self._model_name = model_name
        self._dimensions = dimensions
        self._model_factory = model_factory or _load_sentence_transformer
        self._model: Any | None = None
        self._model_lock = Lock()

    @property
    def provider_name(self) -> str:
        return RagEmbeddingProvider.SENTENCE_TRANSFORMERS.value

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        encoded = self._get_model().encode(list(texts))
        raw_vectors = encoded.tolist() if hasattr(encoded, "tolist") else list(encoded)
        if len(texts) == 1 and raw_vectors and isinstance(raw_vectors[0], (int, float)):
            raw_vectors = [raw_vectors]
        vectors = [list(vector) for vector in raw_vectors]
        if len(vectors) != len(texts):
            raise ValueError(
                "Sentence Transformers response count did not match the requested text count."
            )
        _validate_vectors(vectors, dimensions=self._dimensions, provider_name=self.provider_name)
        return vectors

    def _get_model(self) -> Any:
        if self._model is None:
            with self._model_lock:
                if self._model is None:
                    self._model = self._model_factory(self._model_name)
                    reported_dimensions = self._model.get_sentence_embedding_dimension()
                    if reported_dimensions != self._dimensions:
                        raise ValueError(
                            "Sentence Transformers model reports "
                            f"{reported_dimensions} dimensions; "
                            f"configured dimensions are {self._dimensions}."
                        )
        return self._model


def build_embedding_provider(settings: RagSettings) -> EmbeddingProvider:
    if settings.embedding_provider == RagEmbeddingProvider.OPENAI:
        return OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key or "",
            model_name=settings.model_name,
            dimensions=settings.embedding_dimensions,
        )
    if settings.embedding_provider == RagEmbeddingProvider.SENTENCE_TRANSFORMERS:
        return SentenceTransformerEmbeddingProvider(
            model_name=settings.model_name,
            dimensions=settings.embedding_dimensions,
        )
    raise ValueError(f"Unsupported RAG embedding provider: {settings.embedding_provider!r}")


def get_embedding_provider(
    provider_name: RagEmbeddingProvider,
    model_name: str,
    dimensions: int,
    openai_api_key: str | None = None,
) -> EmbeddingProvider:
    if provider_name == RagEmbeddingProvider.OPENAI:
        return OpenAIEmbeddingProvider(
            api_key=openai_api_key or "",
            model_name=model_name,
            dimensions=dimensions,
        )
    if provider_name == RagEmbeddingProvider.SENTENCE_TRANSFORMERS:
        return SentenceTransformerEmbeddingProvider(
            model_name=model_name,
            dimensions=dimensions,
        )
    raise ValueError(f"Unsupported RAG embedding provider: {provider_name!r}")


def _load_sentence_transformer(model_name: str) -> Any:
    try:
        module = import_module("sentence_transformers")
    except ImportError as exc:
        raise RuntimeError(
            "Sentence Transformers embeddings require the optional local dependency. "
            "Install it with `uv sync --extra local-embeddings`."
        ) from exc
    return module.SentenceTransformer(model_name)


def _validate_vectors(
    vectors: Sequence[Sequence[float]],
    *,
    dimensions: int,
    provider_name: str,
) -> None:
    for index, vector in enumerate(vectors):
        if len(vector) != dimensions:
            raise ValueError(
                f"{provider_name} embedding at index {index} has {len(vector)} dimensions; "
                f"expected {dimensions}."
            )


# Compatibility alias for callers that only need single-query embeddings.
QueryEmbeddingProvider = EmbeddingProvider
