from types import SimpleNamespace

import pytest

from backend.rag.defaults import DEFAULT_RAG_MODEL_NAME
from backend.rag.embeddings import OpenAIEmbeddingProvider


def test_openai_embedding_provider_embeds_query_with_configured_dimensions() -> None:
    client = FakeEmbeddingClient()
    provider = OpenAIEmbeddingProvider(
        embedding_client=client,
        api_key="test-key",
    )

    result = provider.embed_query("What is state?", model_name=DEFAULT_RAG_MODEL_NAME)

    assert result == [0.0, 1.0]
    assert client.calls == [
        {
            "model": DEFAULT_RAG_MODEL_NAME,
            "input": ["What is state?"],
            "dimensions": 384,
        }
    ]


def test_openai_embedding_provider_embeds_documents() -> None:
    client = FakeEmbeddingClient(vectors=[[0.1, 0.2], [0.3, 0.4]])
    provider = OpenAIEmbeddingProvider(
        embedding_client=client,
        api_key="test-key",
    )

    result = provider.embed_documents(
        ["First", "Second"],
        model_name=DEFAULT_RAG_MODEL_NAME,
        embedding_dimensions=384,
    )

    assert result == [[0.1, 0.2], [0.3, 0.4]]


def test_openai_embedding_provider_rejects_missing_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        OpenAIEmbeddingProvider()


def test_openai_embedding_provider_rejects_non_openai_contract() -> None:
    with pytest.raises(ValueError, match="local embedding fallback"):
        OpenAIEmbeddingProvider(
            embedding_provider="sentence-transformers",
            api_key="test-key",
        )


class FakeEmbeddingClient:
    def __init__(self, *, vectors: list[list[float]] | None = None) -> None:
        self.vectors = vectors or [[0.0, 1.0]]
        self.calls = []

    def __call__(self, *, model, input, dimensions):
        self.calls.append(
            {
                "model": model,
                "input": input,
                "dimensions": dimensions,
            }
        )
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=vector) for vector in self.vectors],
        )
