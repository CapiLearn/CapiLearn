import sys
from types import SimpleNamespace

import pytest

from backend.rag.embeddings import (
    OpenAIEmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
)


def test_openai_provider_embeds_single_text_with_configured_dimensions() -> None:
    client = FakeOpenAIClient([[0.1, 0.2, 0.3]])
    provider = OpenAIEmbeddingProvider(
        api_key="test-key",
        model_name="text-embedding-3-small",
        dimensions=3,
        client=client,
    )

    assert provider.embed_text("query") == [0.1, 0.2, 0.3]
    assert client.calls == [
        {
            "model": "text-embedding-3-small",
            "input": ["query"],
            "dimensions": 3,
            "encoding_format": "float",
        }
    ]


def test_openai_provider_preserves_response_order_for_batch() -> None:
    client = FakeOpenAIClient([[0.3, 0.4], [0.1, 0.2]], indexes=[1, 0])
    provider = OpenAIEmbeddingProvider(
        api_key="test-key",
        model_name="text-embedding-3-small",
        dimensions=2,
        client=client,
    )

    assert provider.embed_texts(["first", "second"]) == [[0.1, 0.2], [0.3, 0.4]]


def test_openai_provider_rejects_wrong_embedding_dimensions() -> None:
    provider = OpenAIEmbeddingProvider(
        api_key="test-key",
        model_name="text-embedding-3-small",
        dimensions=3,
        client=FakeOpenAIClient([[0.1, 0.2]]),
    )

    with pytest.raises(ValueError, match="has 2 dimensions; expected 3"):
        provider.embed_text("query")


def test_openai_provider_requires_api_key() -> None:
    with pytest.raises(ValueError, match="OPENAI_API_KEY is required"):
        OpenAIEmbeddingProvider(
            api_key="",
            model_name="text-embedding-3-small",
            dimensions=384,
        )


def test_sentence_transformers_provider_is_lazy_and_supports_batches() -> None:
    sys.modules.pop("sentence_transformers", None)
    factory = CountingModelFactory()
    provider = SentenceTransformerEmbeddingProvider(
        model_name="local-model",
        dimensions=2,
        model_factory=factory,
    )

    assert "sentence_transformers" not in sys.modules
    assert provider.embed_texts(["first", "second"]) == [[0.0, 1.0], [0.0, 1.0]]
    assert factory.calls == ["local-model"]
    assert factory.model.queries == [["first", "second"]]


class FakeOpenAIClient:
    def __init__(self, vectors: list[list[float]], indexes: list[int] | None = None) -> None:
        self.vectors = vectors
        self.indexes = indexes or list(range(len(vectors)))
        self.calls = []
        self.embeddings = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            data=[
                SimpleNamespace(index=index, embedding=vector)
                for index, vector in zip(self.indexes, self.vectors, strict=True)
            ]
        )


class CountingModelFactory:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.model = FakeEmbeddingModel()

    def __call__(self, model_name: str) -> "FakeEmbeddingModel":
        self.calls.append(model_name)
        return self.model


class FakeEmbeddingModel:
    def __init__(self) -> None:
        self.queries: list[list[str]] = []

    def get_sentence_embedding_dimension(self) -> int:
        return 2

    def encode(self, query_texts: list[str]) -> list[list[float]]:
        self.queries.append(query_texts)
        return [[0.0, 1.0] for _ in query_texts]
