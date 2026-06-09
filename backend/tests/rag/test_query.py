import importlib
import sys
import unittest
from types import ModuleType
from unittest.mock import Mock


def make_retriever_module(
    *,
    get_collection=None,
    retrieve_context=None,
    format_context=None,
) -> ModuleType:
    retriever = ModuleType("backend.rag.retriever")
    retriever.get_collection = get_collection or Mock(return_value="collection")
    retriever.retrieve_context = retrieve_context or Mock(return_value=[])
    retriever.format_context = format_context or Mock(return_value="")
    return retriever


def make_embeddings_module(*, provider=None, get_embedding_provider=None) -> ModuleType:
    embeddings = ModuleType("backend.rag.embeddings")
    embeddings.QueryEmbeddingProvider = object
    embeddings.get_embedding_provider = get_embedding_provider or Mock(
        return_value=provider or FakeEmbeddingProvider()
    )
    return embeddings


def fresh_query_module(retriever: ModuleType, embeddings: ModuleType):
    sys.modules.pop("backend.rag.query", None)
    sys.modules["backend.rag.retriever"] = retriever
    sys.modules["backend.rag.embeddings"] = embeddings
    return importlib.import_module("backend.rag.query")


class ChromaRagQueryTests(unittest.TestCase):
    def tearDown(self) -> None:
        query = sys.modules.get("backend.rag.query")
        if query is not None:
            query.get_default_chroma_query_engine.cache_clear()
        sys.modules.pop("backend.rag.query", None)
        sys.modules.pop("backend.rag.retriever", None)
        sys.modules.pop("backend.rag.embeddings", None)

    def test_import_does_not_load_provider_or_collection(self) -> None:
        retriever = make_retriever_module(
            get_collection=Mock(side_effect=AssertionError("collection loaded")),
        )
        embeddings = make_embeddings_module(
            get_embedding_provider=Mock(
                side_effect=AssertionError("provider loaded during import")
            ),
        )

        fresh_query_module(retriever, embeddings)

    def test_chroma_query_engine_embeds_query_and_returns_chunks_and_context(self) -> None:
        chunks = [
            {
                "content": "React state stores component data.",
                "metadata": {"source_path": "src/content/en/state.md"},
                "distance": 0.12,
            }
        ]
        provider = FakeEmbeddingProvider(vector=[0.1, 0.2])
        retriever = make_retriever_module(
            get_collection=Mock(return_value="collection"),
            retrieve_context=Mock(return_value=chunks),
            format_context=Mock(return_value="formatted context"),
        )
        embeddings = make_embeddings_module(provider=provider)
        query = fresh_query_module(retriever, embeddings)

        engine = query.ChromaRagQueryEngine(embedding_provider=provider)
        result = engine.query("What is React state?", top_k=3)

        assert provider.calls == [
            {
                "query_text": "What is React state?",
                "model_name": "sentence-transformers/all-MiniLM-L6-v2",
            }
        ]
        retriever.get_collection.assert_called_once_with(
            "data/vector_store/chroma",
            "capilearn_course_chunks",
        )
        retriever.retrieve_context.assert_called_once_with(
            query_embedding=[0.1, 0.2],
            collection="collection",
            top_k=3,
        )
        retriever.format_context.assert_called_once_with(chunks)
        self.assertEqual(result, {"chunks": chunks, "context": "formatted context"})

    def test_query_chroma_rag_reuses_cached_provider_and_collection(self) -> None:
        provider = FakeEmbeddingProvider(vector=[0.1, 0.2])
        retriever = make_retriever_module(
            get_collection=Mock(return_value="collection"),
            retrieve_context=Mock(return_value=[]),
            format_context=Mock(return_value="No relevant context found."),
        )
        embeddings = make_embeddings_module(provider=provider)
        query = fresh_query_module(retriever, embeddings)

        query.query_chroma_rag("first")
        query.query_chroma_rag("second")

        embeddings.get_embedding_provider.assert_called_once_with()
        retriever.get_collection.assert_called_once_with(
            "data/vector_store/chroma",
            "capilearn_course_chunks",
        )
        assert provider.calls == [
            {
                "query_text": "first",
                "model_name": "sentence-transformers/all-MiniLM-L6-v2",
            },
            {
                "query_text": "second",
                "model_name": "sentence-transformers/all-MiniLM-L6-v2",
            },
        ]
        self.assertEqual(retriever.retrieve_context.call_count, 2)

    def test_backwards_compatible_query_api_uses_chroma_engine(self) -> None:
        provider = FakeEmbeddingProvider(vector=[0.3, 0.4])
        chunks = [
            {
                "content": "Legacy query helper still works.",
                "metadata": {"source_path": "src/content/en/legacy.md"},
                "distance": 0.2,
            }
        ]
        retriever = make_retriever_module(
            get_collection=Mock(return_value="collection"),
            retrieve_context=Mock(return_value=chunks),
            format_context=Mock(return_value="legacy context"),
        )
        embeddings = make_embeddings_module(provider=provider)
        query = fresh_query_module(retriever, embeddings)

        result = query.query_rag("legacy question", top_k=2)

        assert query.RagConfig is query.ChromaRagConfig
        assert query.RagQueryEngine is query.ChromaRagQueryEngine
        assert query.get_default_query_engine is query.get_default_chroma_query_engine
        assert hasattr(query.get_default_query_engine, "cache_clear")
        assert query.get_default_query_engine() is query.get_default_chroma_query_engine()
        assert result == {"chunks": chunks, "context": "legacy context"}
        assert provider.calls == [
            {
                "query_text": "legacy question",
                "model_name": "sentence-transformers/all-MiniLM-L6-v2",
            }
        ]
        retriever.retrieve_context.assert_called_once_with(
            query_embedding=[0.3, 0.4],
            collection="collection",
            top_k=2,
        )


class FakeEmbeddingProvider:
    def __init__(self, *, vector: list[float] | None = None) -> None:
        self.vector = vector or [0.0]
        self.calls = []

    def embed_query(self, query_text: str, *, model_name: str) -> list[float]:
        self.calls.append({"query_text": query_text, "model_name": model_name})
        return self.vector


if __name__ == "__main__":
    unittest.main()
