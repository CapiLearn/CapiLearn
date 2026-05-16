"""
query.py

Lazy public entry point for the RAG retrieval pipeline.

Importing this module does not load the embedding model or connect to the
vector store. Those resources are created only when retrieval is first used,
which keeps FastAPI startup safe and lets callers decide how to handle a
missing local vector store.

Usage::

    from backend.rag.query import query_rag

    result = query_rag("What is React state?")
    # result["chunks"]   -> list of raw chunk dicts (content, metadata, distance)
    # result["context"]  -> formatted context string ready to inject into a prompt
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from .retriever import (
    format_context,
    get_collection,
    get_embedding_model,
    retrieve_context,
)

_DEFAULT_TOP_K = 5


@dataclass(frozen=True)
class RagConfig:
    """Configuration for the local RAG query engine."""

    persist_path: str = "data/vector_store/chroma"
    collection_name: str = "capilearn_course_chunks"
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    top_k: int = _DEFAULT_TOP_K


class RagQueryEngine:
    """Lazy wrapper around the embedding model, vector store, and retriever."""

    def __init__(self, config: RagConfig = RagConfig()) -> None:
        self._config = config
        self._model: Any | None = None
        self._collection: Any | None = None

    @property
    def config(self) -> RagConfig:
        return self._config

    @property
    def model(self) -> Any:
        if self._model is None:
            self._model = get_embedding_model(self._config.model_name)
        return self._model

    @property
    def collection(self) -> Any:
        if self._collection is None:
            self._collection = get_collection(
                self._config.persist_path,
                self._config.collection_name,
            )
        return self._collection

    def retrieve(self, question: str, top_k: int | None = None) -> list[dict]:
        """Retrieve raw context chunks for *question*."""
        n_results = self._config.top_k if top_k is None else top_k
        return retrieve_context(
            question,
            self.collection,
            self.model,
            top_k=n_results,
        )

    def query(self, question: str, top_k: int | None = None) -> dict:
        """Return raw chunks and a formatted context block for *question*."""
        chunks = self.retrieve(question, top_k=top_k)
        context = format_context(chunks)
        return {"chunks": chunks, "context": context}


@lru_cache(maxsize=1)
def get_default_query_engine() -> RagQueryEngine:
    """Return the process-local default RAG query engine."""
    return RagQueryEngine()


def query_rag(question: str, top_k: int = _DEFAULT_TOP_K) -> dict:
    """
    Run the full RAG retrieval pipeline for *question*.

    This backwards-compatible helper uses a cached lazy query engine.
    """
    return get_default_query_engine().query(question, top_k=top_k)
