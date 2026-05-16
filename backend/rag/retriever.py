"""
retriever.py

Queries the local ChromaDB vector store and returns relevant course chunks
for a student question.

Input:
    A natural language student question

Output:
    A ranked list of retrieved chunks with source metadata and distances

Responsibilities:
    - Load the local embedding model
    - Connect to the persisted ChromaDB collection
    - Retrieve relevant course chunks
    - Format retrieved context for future answer generation

This module does not:
    - Generate final student-facing answers
    - Apply guardrails
    - Store memory
    - Expose API endpoints
"""

from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

# Directory that contains this script (backend/rag/)
_HERE = Path(__file__).parent

# The data folder sits one level up, inside the ingestion package
_DATA_DIR = _HERE.parent / "ingestion"

# ---------------------------------------------------------------------------
# Model and collection helpers
# ---------------------------------------------------------------------------


def get_embedding_model(model_name: str) -> SentenceTransformer:
    """Load and return a local SentenceTransformer embedding model."""
    print(f"Loading embedding model '{model_name}' …")
    return SentenceTransformer(model_name)


def get_collection(
    persist_path: str,
    collection_name: str,
) -> chromadb.Collection:
    """
    Connect to the persistent ChromaDB store and return the named collection.

    *persist_path* can be relative (resolved from the ingestion data directory)
    or absolute.
    """
    path = Path(persist_path)
    if not path.is_absolute():
        path = _DATA_DIR / path

    client = chromadb.PersistentClient(path=str(path))
    collection = client.get_collection(name=collection_name)
    return collection


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


def retrieve_context(
    question: str,
    collection: chromadb.Collection,
    model: SentenceTransformer,
    top_k: int = 5,
) -> list[dict]:
    """
    Embed *question* and query *collection* for the *top_k* closest chunks.

    Returns a list of dicts, each containing:
    - content  : the chunk text
    - metadata : the chunk metadata dict
    - distance : cosine distance from the query embedding (lower = more similar)
    """
    query_embedding = model.encode(question).tolist()

    results = collection.query(
        query_embeddings=[query_embedding],
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


# ---------------------------------------------------------------------------
# Entry point – simple command-line test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    PERSIST_PATH = "data/vector_store/chroma"
    COLLECTION_NAME = "capilearn_course_chunks"
    MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
    TOP_K = 5
    TEST_QUESTION = "What is React state?"

    model = get_embedding_model(MODEL_NAME)
    collection = get_collection(PERSIST_PATH, COLLECTION_NAME)

    print(f"\nQuestion: {TEST_QUESTION}\n")
    results = retrieve_context(TEST_QUESTION, collection, model, top_k=TOP_K)

    for i, result in enumerate(results, start=1):
        meta = result["metadata"]
        source = meta.get("source_path") or meta.get("file_name") or "unknown"
        print(f"[{i}] source: {source}  |  distance: {result['distance']:.4f}")
        print(result["content"][:300])
        print()

    print("=== Formatted context block ===")
    print(format_context(results))
