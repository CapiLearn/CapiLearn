"""
retriever.py

Queries a legacy local ChromaDB vector store for historical evaluation tooling.

Input:
    A natural language student question

Output:
    A ranked list of retrieved chunks with source metadata and distances

Responsibilities:
    - Connect to the persisted ChromaDB collection
    - Retrieve relevant course chunks
    - Format retrieved context for future answer generation

This module does not:
    - Generate final student-facing answers
    - Apply guardrails
    - Store memory
    - Expose API endpoints
    - Provide a supported application runtime backend
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

# Directory that contains this script (backend/rag/)
_HERE = Path(__file__).parent

# The data folder sits one level up, inside the ingestion package
_DATA_DIR = _HERE.parent / "ingestion"


def get_collection(
    persist_path: str,
    collection_name: str,
) -> Any:
    """
    Connect to the persistent ChromaDB store and return the named collection.

    *persist_path* can be relative (resolved from the ingestion data directory)
    or absolute.
    """
    path = Path(persist_path)
    if not path.is_absolute():
        path = _DATA_DIR / path

    try:
        import chromadb
    except ImportError as exc:
        raise RuntimeError(
            "Legacy Chroma tooling requires `uv sync --extra legacy-chroma`."
        ) from exc

    client = chromadb.PersistentClient(path=str(path))
    collection = client.get_collection(name=collection_name)
    return collection


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


def retrieve_context(
    *,
    query_embedding: Sequence[float],
    collection: Any,
    top_k: int = 5,
) -> list[dict]:
    """
    Query *collection* for the *top_k* closest chunks using *query_embedding*.

    Returns a list of dicts, each containing:
    - content  : the chunk text
    - metadata : the chunk metadata dict
    - distance : cosine distance from the query embedding (lower = more similar)
    """
    results = collection.query(
        query_embeddings=[list(query_embedding)],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    retrieved: list[dict] = []
    # collection.query returns parallel lists wrapped in an outer list (one per query)
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    for content, metadata, distance in zip(documents, metadatas, distances):
        retrieved.append(
            {
                "content": content,
                "metadata": metadata,
                "distance": distance,
            }
        )

    return retrieved


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_context(results: list[dict]) -> str:
    """
    Format retrieved chunks into a readable context block.

    Intended to be inserted into a future LLM prompt as the knowledge
    context section.
    """
    if not results:
        return "No relevant context found."

    lines: list[str] = []
    for i, result in enumerate(results, start=1):
        meta = result["metadata"]
        source = meta.get("source_path") or meta.get("file_name") or "unknown"
        distance = result["distance"]
        lines.append(f"--- Chunk {i} | source: {source} | distance: {distance:.4f} ---")
        lines.append(result["content"])
        lines.append("")  # blank line between chunks

    return "\n".join(lines).strip()
