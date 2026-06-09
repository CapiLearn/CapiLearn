# RAG Layer - Architecture

## Purpose

The RAG layer turns course source files into searchable embeddings and supplies
relevant course context to the chat generation flow. PostgreSQL with pgvector
is the preferred runtime for this branch. The existing Chroma implementation
remains available through `RAG_BACKEND=chroma` as a rollback path.

The RAG layer retrieves context; the existing LLM service remains responsible
for guardrails, prompt construction, generation, and response handling.

## End-to-End Flow

```text
Raw course repository
    |
    | backend/ingestion/ingest_pgvector.py
    | - reads supported files
    | - filters English source paths
    | - applies Markdown-aware chunking
    | - generates 384-dimensional embeddings
    v
PostgreSQL
    rag_documents
    rag_chunks
    rag_embeddings vector(384)
    rag_retrieval_logs
    |
    | cosine similarity search through pgvector
    v
RAG retrieval provider
    |
    | RetrievalResult / RetrievedChunk
    v
LLMService
    |
    | build_messages() injects retrieved context
    v
Chat generation
```

Input guardrail evaluation and retrieval still run concurrently. Query
embedding uses a worker thread because `sentence-transformers` is synchronous;
the pgvector query uses the asynchronous SQLAlchemy session layer.

The verified local corpus contains 72 documents, 2,353 chunks, and 2,353
embeddings. These counts describe the current bundled corpus and may change
when its source files or chunking configuration change.

## Ingestion

`backend/ingestion/ingest_pgvector.py` reads the raw course repository directly
and reuses:

- `find_course_files()` and `make_document()` from `ingest_repo.py`
- `is_english_source()` and `chunk_document()` from `chunk_documents.py`
- `sentence-transformers/all-MiniLM-L6-v2` for embeddings

Chunking splits on Markdown headings, then applies a 1,000-character sliding
window with 200-character overlap to oversized sections.

Each document is replaced atomically. A rerun updates the matching
`(source_type, source_path)` document, deletes its old chunks and embeddings,
and writes the replacement records in one transaction.

## Storage

- `rag_documents` stores source identity, content hashes, and source metadata.
- `rag_chunks` stores chunk text, order, and chunk metadata.
- `rag_embeddings` stores one `vector(384)` embedding per chunk.
- `rag_retrieval_logs` stores the query, retrieved chunk IDs, cosine distances,
  similarities, and optional RAG index version when
  `RAG_WRITE_RETRIEVAL_LOGS=true`.

The embedding column has an HNSW index using `vector_cosine_ops`.

## Runtime Retrieval

`backend/rag/retrieval.py` implements both providers behind the
`RetrievalProvider` protocol from `backend/rag/schemas.py`:

- `PgvectorRagRetrievalProvider` embeds the query, then delegates vector
  retrieval to `RagService`.
- `ChromaRagRetrievalProvider` preserves the legacy Chroma path for rollback.

`RAG_BACKEND` selects the provider at application startup. Both providers
return `RetrievalResult` containing `RetrievedChunk` objects, so prompt behavior
does not change. Retrieval errors propagate to `LLMService`, which logs
`rag.retrieve.failed`, degrades to empty context, and still allows generation.

Both runtime retrieval backends use `backend/rag/embeddings.py` for query-time
`SentenceTransformer` loading, caching, and lock handling. Chroma's query
engine owns text-query embedding plus collection lookup for rollback and dev
scripts; pgvector still owns database retrieval and logging.

The verified pgvector path embeds the query with
`sentence-transformers/all-MiniLM-L6-v2`, filters stored embeddings by the same
model name, orders results by cosine distance, and returns `RAG_TOP_K` chunks.
The default configured value is five chunks.

## Prompt Injection

`LLMService` starts retrieval while input guardrails run. After guardrails pass,
the retrieved chunks are passed to `build_messages()`.

`backend/llm/prompts.py` wraps those chunks in a `<retrieved_context>` block
before the student message. No separate retrieval endpoint or frontend change
is required.

Structured runtime events include `rag.provider.retrieve.completed` with
`backend=pgvector`, chunk count, source paths, distances, and similarities.
`rag.retrieve.completed` records successful chunks accepted by `LLMService`.
Retrieval failures emit `rag.retrieve.failed` without a matching
`rag.retrieve.completed` event. There is no separate prompt-injection event;
successful retrieval followed by
`llm.generation.completed` exercises the existing `build_messages()` context
injection path.

## Chroma Fallback

Chroma remains available for fallback and rollback:

```dotenv
RAG_BACKEND=chroma
```

Its JSON preprocessing, vector-store builder, query engine, and evaluation
script have not been removed.

If `RAG_BACKEND` is omitted, the current code-level settings default remains
Chroma. The branch's `.env.example` explicitly selects pgvector, so copy or set
that value before starting FastAPI.

## Known Limitations

- Retrieval uses semantic cosine similarity only.
- There is no hybrid keyword search, reranking, metadata filtering, or score
  threshold.
- Retrieval quality depends on the fixed English source-path convention.
- Chunks may retain Markdown, HTML fragments, frontmatter, and code blocks.
- Removed source files are not automatically deleted from PostgreSQL.
- Retrieval quality evaluation remains manual and qualitative.
- The first embedding-model use may require a network download.
- Retrieval failures intentionally produce empty context, which can reduce
  answer grounding without failing the chat turn.
