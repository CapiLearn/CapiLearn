from backend.rag.embeddings import SentenceTransformerEmbeddingProvider


def test_embedding_provider_reuses_model_for_same_model_name() -> None:
    factory = CountingModelFactory()
    provider = SentenceTransformerEmbeddingProvider(model_factory=factory)

    first = provider.embed_query("first", model_name="model-a")
    second = provider.embed_query("second", model_name="model-a")

    assert first == [0.0, 1.0]
    assert second == [0.0, 1.0]
    assert factory.calls == ["model-a"]
    assert factory.models["model-a"].queries == ["first", "second"]


def test_embedding_provider_loads_separate_models_by_model_name() -> None:
    factory = CountingModelFactory()
    provider = SentenceTransformerEmbeddingProvider(model_factory=factory)

    provider.embed_query("first", model_name="model-a")
    provider.embed_query("second", model_name="model-b")

    assert factory.calls == ["model-a", "model-b"]
    assert factory.models["model-a"].queries == ["first"]
    assert factory.models["model-b"].queries == ["second"]


def test_embedding_provider_normalizes_tolist_embedding_results() -> None:
    provider = SentenceTransformerEmbeddingProvider(
        model_factory=lambda name: FakeEmbeddingModel(VectorWithToList([0.2, 0.8]))
    )

    assert provider.embed_query("query", model_name="model-a") == [0.2, 0.8]


def test_embedding_provider_normalizes_list_like_embedding_results() -> None:
    provider = SentenceTransformerEmbeddingProvider(
        model_factory=lambda name: FakeEmbeddingModel((0.3, 0.7))
    )

    assert provider.embed_query("query", model_name="model-a") == [0.3, 0.7]


class CountingModelFactory:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.models: dict[str, FakeEmbeddingModel] = {}

    def __call__(self, model_name: str) -> "FakeEmbeddingModel":
        self.calls.append(model_name)
        model = FakeEmbeddingModel([0.0, 1.0])
        self.models[model_name] = model
        return model


class FakeEmbeddingModel:
    def __init__(self, vector) -> None:
        self.vector = vector
        self.queries: list[str] = []

    def encode(self, query_text: str):
        self.queries.append(query_text)
        return self.vector


class VectorWithToList:
    def __init__(self, vector: list[float]) -> None:
        self._vector = vector

    def tolist(self) -> list[float]:
        return self._vector
