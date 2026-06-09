"""
evaluate_retrieval.py

Runs a small manual evaluation suite against the local RAG retriever.

Purpose:
    Help developers inspect whether retrieval returns relevant course chunks
    before connecting the RAG layer to answer generation, memory, guardrails,
    or API endpoints.

This module does not:
    - Score retrieval automatically
    - Generate final student answers
    - Modify the vector store
"""

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.rag.query import ChromaRagConfig, ChromaRagQueryEngine  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PERSIST_PATH = "data/vector_store/chroma"
COLLECTION_NAME = "capilearn_course_chunks"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
TOP_K = 5

# ---------------------------------------------------------------------------
# Sample evaluation questions
# ---------------------------------------------------------------------------

SAMPLE_QUESTIONS: list[str] = [
    "What is React state?",
    "How do props work in React?",
    "What is useEffect used for?",
    "What is prop drilling?",
    "How do I fetch data from a backend in React?",
]

# ---------------------------------------------------------------------------
# Evaluation helper
# ---------------------------------------------------------------------------


def print_results(question: str, results: list[dict]) -> None:
    """
    Print the retrieved chunks for a single question in a readable format.

    For each chunk the following is shown:
    - rank
    - source_path from metadata
    - cosine distance (lower = more similar)
    - first 400 characters of content
    """
    separator = "=" * 70
    print(separator)
    print(f"Question: {question}")
    print(separator)

    if not results:
        print("  No results returned.\n")
        return

    for rank, result in enumerate(results, start=1):
        meta = result["metadata"]
        source = meta.get("source_path") or meta.get("file_name") or "unknown"
        distance = result["distance"]
        preview = result["content"][:400]

        print(f"  [{rank}] source   : {source}")
        print(f"       distance : {distance:.4f}")
        print(f"       content  : {preview}")
        if len(result["content"]) > 400:
            print("                 … (truncated)")
        print()


# ---------------------------------------------------------------------------
# Main evaluation loop
# ---------------------------------------------------------------------------


def run_evaluation(
    questions: list[str],
    persist_path: str,
    collection_name: str,
    model_name: str,
    top_k: int,
) -> None:
    """
    Load the Chroma query engine once, then evaluate every question in
    *questions*, printing results to stdout.
    """
    engine = ChromaRagQueryEngine(
        ChromaRagConfig(
            persist_path=persist_path,
            collection_name=collection_name,
            model_name=model_name,
            top_k=top_k,
        )
    )

    print(f"\nRunning retrieval evaluation — {len(questions)} question(s), top_k={top_k}\n")

    for question in questions:
        results = engine.retrieve(question, top_k=top_k)
        print_results(question, results)

    print("Evaluation complete.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    run_evaluation(
        questions=SAMPLE_QUESTIONS,
        persist_path=PERSIST_PATH,
        collection_name=COLLECTION_NAME,
        model_name=MODEL_NAME,
        top_k=TOP_K,
    )
