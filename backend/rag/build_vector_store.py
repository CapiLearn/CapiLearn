"""
build_vector_store.py

Builds a local ChromaDB vector store from processed course chunks.

Input:
    data/processed/chunks.json

Output:
    data/vector_store/chroma/

Responsibilities:
    - Load chunked course content
    - Generate local embeddings using sentence-transformers
    - Store chunk text, IDs, and metadata in ChromaDB

This module does not:
    - Chunk source documents
    - Retrieve context for student questions
    - Generate final student answers
    - Call external LLM services
"""

import json
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

# Directory that contains this script (backend/rag/)
_HERE = Path(__file__).parent

# The data folder sits one level up, inside the ingestion package
_DATA_DIR = _HERE.parent / "ingestion"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_chunks(input_path: str) -> list[dict]:
    """Load chunks from a JSON file and return them as a list of dicts."""
    path = Path(input_path)
    if not path.is_absolute():
        path = _DATA_DIR / path
    with path.open(encoding="utf-8") as f:
        chunks = json.load(f)
    return chunks


# ---------------------------------------------------------------------------
# Metadata cleaning
# ---------------------------------------------------------------------------


def clean_metadata(chunk: dict) -> dict:
    """
    Build a flat metadata dict suitable for ChromaDB.

    ChromaDB only accepts scalar metadata values (str, int, float, bool).
    - None values are converted to empty strings.
    - chunk_index is stored as an int.
    - document_id is copied from the top-level chunk field.
    """
    raw: dict = chunk.get("metadata", {})

    return {
        "source_path": raw.get("source_path") or "",
        "file_name": raw.get("file_name") or "",
        "file_type": raw.get("file_type") or "",
        "week": raw.get("week") or "",
        "day": raw.get("day") or "",
        "document_id": chunk.get("document_id") or "",
        "chunk_index": int(chunk.get("chunk_index", 0)),
    }


# ---------------------------------------------------------------------------
# Vector store builder
# ---------------------------------------------------------------------------


def build_vector_store(
    chunks_path: str,
    persist_path: str,
    collection_name: str,
    model_name: str,
) -> None:
    """
    Load chunks, embed them, and persist them in a ChromaDB collection.

    Steps:
    1. Load chunks from *chunks_path*.
    2. Validate that every chunk has non-empty content.
    3. Initialise the SentenceTransformer embedding model.
    4. Create (or reset) the ChromaDB collection at *persist_path*.
    5. Embed all chunk contents in a single batch.
    6. Add everything to Chroma with cleaned metadata.
    7. Print a summary.
    """
    # 1. Load chunks
    chunks = load_chunks(chunks_path)
    print(f"Loaded {len(chunks)} chunk(s) from '{chunks_path}'.")

    # 2. Validate – drop chunks with empty content and warn
    valid_chunks = [c for c in chunks if c.get("content", "").strip()]
    skipped = len(chunks) - len(valid_chunks)
    if skipped:
        print(f"Warning: skipped {skipped} chunk(s) with empty content.")

    if not valid_chunks:
        print("No valid chunks to embed. Exiting.")
        return

    # 3. Initialise the local embedding model
    print(f"Loading embedding model '{model_name}' …")
    model = SentenceTransformer(model_name)

    # 4. Initialise a persistent ChromaDB client
    persist_dir = Path(persist_path)
    if not persist_dir.is_absolute():
        persist_dir = _DATA_DIR / persist_dir
    persist_dir.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(persist_dir))

    # 5. Create or reset the collection
    #    delete_collection raises if it doesn't exist, so we guard against that
    existing_names = [c.name for c in client.list_collections()]
    if collection_name in existing_names:
        client.delete_collection(collection_name)
        print(f"Existing collection '{collection_name}' deleted (will be rebuilt).")

    collection = client.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )
    print(f"Created collection '{collection_name}'.")

    # 6. Embed all content in one batch (faster than one-by-one)
    contents: list[str] = [c["content"] for c in valid_chunks]
    print(f"Generating embeddings for {len(contents)} chunk(s) …")
    embeddings = model.encode(contents, show_progress_bar=True).tolist()

    # Prepare parallel lists for Chroma
    ids: list[str] = [c["chunk_id"] for c in valid_chunks]
    metadatas: list[dict] = [clean_metadata(c) for c in valid_chunks]

    # Add in batches to avoid potential memory issues with very large datasets
    batch_size = 500
    total_added = 0
    for start in range(0, len(ids), batch_size):
        end = start + batch_size
        collection.add(
            ids=ids[start:end],
            documents=contents[start:end],
            embeddings=embeddings[start:end],
            metadatas=metadatas[start:end],
        )
        total_added += len(ids[start:end])

    # 7. Summary
    print(f"Done. {total_added} chunk(s) added to '{collection_name}'.")
    print(f"Vector store persisted at: {persist_dir.resolve()}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    build_vector_store(
        chunks_path="data/processed/chunks.json",
        persist_path="data/vector_store/chroma",
        collection_name="capilearn_course_chunks",
        model_name="sentence-transformers/all-MiniLM-L6-v2",
    )
