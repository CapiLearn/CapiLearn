"""
query.py

Public entry point for the RAG pipeline, intended to be imported by a
FastAPI route.  The embedding model and ChromaDB collection are loaded once
at import time and reused across all requests.

Usage (from a FastAPI route)::

    from backend.rag.query import query_rag

    result = query_rag("What is React state?")
    # result["chunks"]   → list of raw chunk dicts (content, metadata, distance)
    # result["context"]  → formatted context string ready to inject into an LLM prompt

Public API:
    query_rag(question: str, top_k: int = 5) -> dict
"""

from .retriever import (
    format_context,
    get_collection,
    get_embedding_model,
    retrieve_context,
)

# ---------------------------------------------------------------------------
# Configuration — mirrors the defaults used in retriever.py
# ---------------------------------------------------------------------------

_PERSIST_PATH = "data/vector_store/chroma"
_COLLECTION_NAME = "capilearn_course_chunks"
_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_DEFAULT_TOP_K = 5

# ---------------------------------------------------------------------------
# Singletons — loaded once when the module is first imported
# ---------------------------------------------------------------------------

_model = get_embedding_model(_MODEL_NAME)
_collection = get_collection(_PERSIST_PATH, _COLLECTION_NAME)

# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def query_rag(question: str, top_k: int = _DEFAULT_TOP_K) -> dict:
    """
    Run the full RAG retrieval pipeline for *question*.

    Parameters
    ----------
    question:
        The student's natural-language question.
    top_k:
        Number of chunks to retrieve (default 5).

    Returns
    -------
    dict with two keys:
    - ``chunks``  : list of dicts, each with ``content``, ``metadata``, and
                    ``distance`` keys (raw retriever output).
    - ``context`` : formatted string suitable for injecting into an LLM prompt.
    """
    chunks = retrieve_context(question, _collection, _model, top_k=top_k)
    context = format_context(chunks)
    return {"chunks": chunks, "context": context}
