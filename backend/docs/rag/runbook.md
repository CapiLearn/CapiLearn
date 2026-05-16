# RAG Layer — Runbook

## Purpose

This runbook explains how to run, rebuild, and evaluate the RAG pipeline for CapiLearn. It covers the full pipeline from raw course content to a working vector store, and describes how to inspect retrieval quality manually.

## Prerequisites

- Python 3.11+
- Dependencies installed (see root `pyproject.toml` or `requirements.txt`):
  - `chromadb`
  - `sentence-transformers`
- The raw Full Stack Open repository cloned to:
  `backend/ingestion/data/raw/fullstack-hy2020.github.io/`

## Expected Directory Structure

After running the full pipeline, the following files and folders should exist:

```
backend/ingestion/data/
    raw/
        fullstack-hy2020.github.io/   ← raw course repo (cloned manually)
    processed/
        documents.json                ← output of ingest_repo.py
        chunks.json                   ← output of chunk_documents.py
    vector_store/
        chroma/                       ← output of build_vector_store.py
```

## Run Order

The scripts must be run in order. Each step depends on the output of the previous one.

### From the project root

```bash
python backend/ingestion/ingest_repo.py
python backend/rag/chunk_documents.py
python backend/rag/build_vector_store.py
```

### From `backend/rag/`

```bash
python ../ingestion/ingest_repo.py
python chunk_documents.py
python build_vector_store.py
```

## Expected Outputs

### `ingest_repo.py`

Writes `backend/ingestion/data/processed/documents.json`.

Each entry has this shape:
```json
{
  "id": "src/content/9/en/part9d.md",
  "content": "...",
  "metadata": {
    "source_path": "src/content/9/en/part9d.md",
    "file_name": "part9d.md",
    "file_type": ".md",
    "week": "9",
    "day": "d"
  }
}
```

### `chunk_documents.py`

Prints:
```
Loaded N source document(s) from 'data/processed/documents.json'.
Selected M English document(s) (filtered by '/en/' in source_path).
Created K chunk(s). Saved to 'data/processed/chunks.json'.
```

Writes `backend/ingestion/data/processed/chunks.json`.

Each chunk has this shape:
```json
{
  "chunk_id": "<uuid>",
  "document_id": "src/content/9/en/part9d.md",
  "chunk_index": 0,
  "content": "...",
  "metadata": { ... }
}
```

### `build_vector_store.py`

Prints progress including embedding generation and chunk insertion count.

Persists the ChromaDB collection to `backend/ingestion/data/vector_store/chroma/`.

The collection is **reset on every run**, so rebuilding always starts from a clean state.

## Manual Retrieval Evaluation

Run the evaluation script to inspect retrieval quality for a fixed set of sample questions:

```bash
# From project root
python backend/rag/evaluate_retrieval.py

# From backend/rag/
python evaluate_retrieval.py
```

For each question, the script prints the top 5 retrieved chunks with:
- rank
- `source_path`
- cosine distance (lower = more similar)
- first 400 characters of content

Read the output and check whether the returned chunks are relevant to the question. There is no automated scoring at this time.

## Troubleshooting

### `FileNotFoundError: documents.json`

The ingestion script has not been run yet, or was run from the wrong directory.

Run `ingest_repo.py` first. All scripts resolve data paths relative to `backend/ingestion/`, not the current working directory.

### `FileNotFoundError: chunks.json`

`chunk_documents.py` has not been run yet, or `documents.json` is empty.

Check that `documents.json` exists and contains entries before running the chunking step.

### `CollectionNotFoundError` (ChromaDB)

The vector store has not been built yet, or was deleted.

Run `build_vector_store.py` to create the collection.

### `Selected 0 English document(s)`

No documents in `documents.json` have a `source_path` containing `/en/`. This usually means either:
- The raw repo was not cloned to the expected location, or
- `ingest_repo.py` produced paths that do not include the `/en/` segment.

Check the `source_path` values in `documents.json` directly.

### Embedding model download on first run

`sentence-transformers` will download `all-MiniLM-L6-v2` from Hugging Face on first use and cache it locally. This requires an internet connection the first time only.

## Rebuilding the Vector Store

To fully rebuild from scratch (e.g. after adding new course content or changing chunk settings), run the three scripts in the order shown in [Run Order](#run-order).

`build_vector_store.py` deletes and recreates the ChromaDB collection on every run, so no manual cleanup of the vector store is needed.
