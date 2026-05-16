import importlib
import sys
import unittest
from types import ModuleType
from unittest.mock import Mock


def make_retriever_module(
    *,
    get_embedding_model=None,
    get_collection=None,
    retrieve_context=None,
    format_context=None,
) -> ModuleType:
    retriever = ModuleType("backend.rag.retriever")
    retriever.get_embedding_model = get_embedding_model or Mock(return_value="model")
    retriever.get_collection = get_collection or Mock(return_value="collection")
    retriever.retrieve_context = retrieve_context or Mock(return_value=[])
    retriever.format_context = format_context or Mock(return_value="")
    return retriever


def fresh_query_module(retriever: ModuleType):
    sys.modules.pop("backend.rag.query", None)
    sys.modules["backend.rag.retriever"] = retriever
    return importlib.import_module("backend.rag.query")


class RagQueryTests(unittest.TestCase):
    def tearDown(self) -> None:
        query = sys.modules.get("backend.rag.query")
        if query is not None:
            query.get_default_query_engine.cache_clear()
        sys.modules.pop("backend.rag.query", None)
        sys.modules.pop("backend.rag.retriever", None)

    def test_import_does_not_load_model_or_collection(self) -> None:
        retriever = make_retriever_module(
            get_embedding_model=Mock(side_effect=AssertionError("model loaded during import")),
            get_collection=Mock(side_effect=AssertionError("collection loaded during import")),
        )

        fresh_query_module(retriever)

    def test_query_rag_loads_lazily_and_returns_chunks_and_context(self) -> None:
        chunks = [
            {
                "content": "React state stores component data.",
                "metadata": {"source_path": "src/content/en/state.md"},
                "distance": 0.12,
            }
        ]
        retriever = make_retriever_module(
            get_embedding_model=Mock(return_value="model"),
            get_collection=Mock(return_value="collection"),
            retrieve_context=Mock(return_value=chunks),
            format_context=Mock(return_value="formatted context"),
        )
        query = fresh_query_module(retriever)

        result = query.query_rag("What is React state?", top_k=3)

        retriever.get_embedding_model.assert_called_once_with(
            "sentence-transformers/all-MiniLM-L6-v2"
        )
        retriever.get_collection.assert_called_once_with(
            "data/vector_store/chroma",
            "capilearn_course_chunks",
        )
        retriever.retrieve_context.assert_called_once_with(
            "What is React state?",
            "collection",
            "model",
            top_k=3,
        )
        retriever.format_context.assert_called_once_with(chunks)
        self.assertEqual(result, {"chunks": chunks, "context": "formatted context"})

    def test_query_rag_reuses_cached_model_and_collection(self) -> None:
        retriever = make_retriever_module(
            get_embedding_model=Mock(return_value="model"),
            get_collection=Mock(return_value="collection"),
            retrieve_context=Mock(return_value=[]),
            format_context=Mock(return_value="No relevant context found."),
        )
        query = fresh_query_module(retriever)

        query.query_rag("first")
        query.query_rag("second")

        retriever.get_embedding_model.assert_called_once_with(
            "sentence-transformers/all-MiniLM-L6-v2"
        )
        retriever.get_collection.assert_called_once_with(
            "data/vector_store/chroma",
            "capilearn_course_chunks",
        )
        self.assertEqual(retriever.retrieve_context.call_count, 2)


if __name__ == "__main__":
    unittest.main()
