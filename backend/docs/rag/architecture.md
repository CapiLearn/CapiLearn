# RAG Layer — Architecture

## Purpose

The RAG (Retrieval-Augmented Generation) layer is responsible for turning raw course content into semantically searchable chunks and retrieving the most relevant chunks for a given student question. It provides context to a future answer-generation layer; it does not generate answers itself.

## Current Scope

- Loading and chunking processed course documents
- Filtering documents to English-language content only
- Generating local embeddings using `sentence-transformers/all-MiniLM-L6-v2`
- Persisting embeddings in a local ChromaDB vector store
- Querying the vector store by semantic similarity to return ranked context chunks
- Manual evaluation of retrieval quality

## Out of Scope

The following are explicitly not handled by this layer at this time:

- Generating final student-facing answers
- Enforcing Socratic tutoring behavior
- Applying input or output guardrails
- Storing student memory or conversation history
- Exposing FastAPI endpoints
- Handling authentication or authorization
- Frontend behavior of any kind

## Data Flow

All `data/` paths below are relative to `backend/ingestion/`.

```
Raw Full Stack Open repo (src/)
    │
    ▼  backend/ingestion/ingest_repo.py
backend/ingestion/data/processed/documents.json
    │
    ▼  backend/rag/chunk_documents.py
backend/ingestion/data/processed/chunks.json
    │
    ▼  backend/rag/build_vector_store.py
backend/ingestion/data/vector_store/chroma/
    │
    ▼  backend/rag/retriever.py
Retrieved course context (list of dicts: content, metadata, distance)
```

## File Responsibilities

| File | Responsibility |
|---|---|
| `backend/ingestion/ingest_repo.py` | Walks the raw course repo, reads supported file types (`.md`, `.txt`, `.py`, `.ipynb`), and writes one document per file to `documents.json` |
| `backend/rag/chunk_documents.py` | Loads `documents.json`, filters to English-only sources, splits documents into smaller chunks using Markdown-aware splitting with character-count fallback, writes `chunks.json` |
| `backend/rag/build_vector_store.py` | Loads `chunks.json`, embeds all content locally, and inserts into a persistent ChromaDB collection (collection is reset on each run) |
| `backend/rag/retriever.py` | Embeds a question, queries ChromaDB, and returns the top-k chunks with content, metadata, and cosine distance |
| `backend/rag/evaluate_retrieval.py` | Runs a fixed set of sample questions through the retriever and prints results to stdout for manual inspection |

## Retrieval Strategy

Retrieval is based on cosine similarity between the query embedding and chunk embeddings, both produced by the same local model (`all-MiniLM-L6-v2`). No keyword boosting, reranking, or hybrid search is applied at this time.

Chunking uses a two-pass approach:
1. Split on Markdown headings (`#`–`######`) to produce semantically coherent sections.
2. For sections exceeding the chunk size (default 1000 characters), apply a sliding window split with overlap (default 200 characters).

English filtering is applied before chunking. A document is considered English if its `source_path` contains `/en/` (or `\en\` on Windows).

## Evaluation Strategy

Evaluation is currently manual and qualitative. `evaluate_retrieval.py` runs a fixed list of sample questions and prints the top-5 retrieved chunks with source path, cosine distance, and a content preview. A contributor reads the output and judges whether the returned chunks are relevant.

There is no automated scoring (e.g. recall@k, MRR, NDCG) at this time.

## Known Limitations

- **Semantic similarity only.** Retrieval does not use keyword matching. Queries that use different vocabulary than the course text may retrieve poor results.
- **No reranking.** The top-k results are returned in raw similarity order without a second-pass reranker.
- **Beginner/advanced mismatch.** A beginner question may retrieve advanced course sections if they are semantically similar at the embedding level.
- **English filter depends on path conventions.** The `/en/` filter works for Full Stack Open's directory structure. Content from other sources with different conventions will not be filtered correctly.
- **Raw Markdown in chunks.** Chunks may still contain Markdown syntax, HTML fragments, frontmatter, or code blocks. No post-processing strips these.
- **Manual evaluation only.** There is no automated test suite for retrieval quality.
- **Retriever returns context only.** The caller is responsible for composing a prompt and generating a final answer.

## Future Improvements

- Add a reranker pass (e.g. cross-encoder) to improve result ordering
- Strip Markdown/HTML/frontmatter from chunks at ingestion time
- Add automated retrieval evaluation with labelled question–document pairs
- Support multiple course sources beyond Full Stack Open
- Expose retrieval as a FastAPI endpoint with request/response validation
- Add metadata filters (e.g. restrict retrieval to a specific course week)
