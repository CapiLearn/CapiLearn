"""
query.py

Lazy public entry point for the Chroma RAG retrieval pipeline.

Importing this module does not load the embedding model or connect to the
vector store. Those resources are created only when retrieval is first used,
which keeps FastAPI startup safe and lets callers decide how to handle a
missing local vector store.

Usage::

    from backend.rag.query import query_chroma_rag

    result = query_chroma_rag("What is React state?")
    # result["chunks"]   -> list of raw chunk dicts (content, metadata, distance)
    # result["context"]  -> formatted context string ready to inject into a prompt
"""

from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from .defaults import (
    DEFAULT_CHROMA_COLLECTION_NAME,
    DEFAULT_CHROMA_PERSIST_PATH,
    DEFAULT_RAG_MODEL_NAME,
    DEFAULT_RAG_TOP_K,
)
from .embeddings import QueryEmbeddingProvider, get_embedding_provider
from .retriever import (
    format_context,
    get_collection,
    retrieve_context,
)


@dataclass(frozen=True)
class ChromaRagConfig:
    """Configuration for the local Chroma RAG query engine."""

    persist_path: str = DEFAULT_CHROMA_PERSIST_PATH
    collection_name: str = DEFAULT_CHROMA_COLLECTION_NAME
    model_name: str = DEFAULT_RAG_MODEL_NAME
    top_k: int = DEFAULT_RAG_TOP_K


class ChromaRagQueryEngine:
    """Lazy wrapper around the shared embedding provider and Chroma collection."""

    def __init__(
        self,
        config: ChromaRagConfig = ChromaRagConfig(),
        *,
        embedding_provider: QueryEmbeddingProvider | None = None,
    ) -> None:
        self._config = config
        self._embedding_provider = embedding_provider or get_embedding_provider()
        self._collection: Any | None = None

    @property
    def config(self) -> ChromaRagConfig:
        return self._config

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
        query_embedding = self._embedding_provider.embed_query(
            question,
            model_name=self._config.model_name,
        )
        return self._retrieve_by_embedding(query_embedding, top_k=top_k)

    def _retrieve_by_embedding(
        self,
        query_embedding: Sequence[float],
        top_k: int | None = None,
    ) -> list[dict]:
        """Retrieve raw context chunks for an already-computed query embedding."""
        n_results = self._config.top_k if top_k is None else top_k
        return retrieve_context(
            query_embedding=query_embedding,
            collection=self.collection,
            top_k=n_results,
        )

    def query(self, question: str, top_k: int | None = None) -> dict:
        """Return raw chunks and a formatted context block for *question*."""
        chunks = self.retrieve(question, top_k=top_k)
        context = format_context(chunks)
        return {"chunks": chunks, "context": context}


@lru_cache(maxsize=1)
def get_default_chroma_query_engine() -> ChromaRagQueryEngine:
    """Return the process-local default Chroma RAG query engine."""
    return ChromaRagQueryEngine()


def query_chroma_rag(
    question: str,
    top_k: int = DEFAULT_RAG_TOP_K,
    *,
    model_name: str = DEFAULT_RAG_MODEL_NAME,
) -> dict:
    """
    Run the full Chroma RAG retrieval pipeline for *question*.

    This helper uses a cached lazy query engine for the default embedding model.
    """
    if model_name == DEFAULT_RAG_MODEL_NAME:
        engine = get_default_chroma_query_engine()
    else:
        engine = ChromaRagQueryEngine(ChromaRagConfig(model_name=model_name))
    return engine.query(question, top_k=top_k)
