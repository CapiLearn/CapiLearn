# RAG Layer - Architecture

## Purpose

The RAG layer converts course source files into structured, searchable chunks
and supplies retained retrieval results to the existing chat generation flow.
PostgreSQL with pgvector is the only supported runtime backend. Runtime
embeddings are generated through the OpenAI embedding provider.

The RAG layer owns source ingestion, chunk contracts, embeddings, retrieval,
deduplication, and retrieval tracing. `LLMService` continues to own guardrails,
prompt construction, generation, and response handling.

## End-to-End Flow

```text
Raw course repository
    |
    | source loading and English-path filtering
    v
markdown-structure-v3
    | typed chunks, UUIDv5 IDs, hashes, offsets, headings, types
    v
PostgreSQL / pgvector
    | active documents only, cosine candidate retrieval
    v
bounded candidate oversampling
    |
    v
conservative deduplication and final top-k
    |
    v
compact source labels in <retrieved_context>
    |
    v
LLMService and chat generation
```

Input guardrail evaluation and retrieval run concurrently. Query embedding runs
through the OpenAI embedding provider; pgvector queries use asynchronous
SQLAlchemy sessions.

The June 10, 2026 verified active corpus contains 72 documents, 4,274 chunks,
and 4,274 embeddings. All active chunks use `markdown-structure-v3`.

## Source Loading and Ingestion

`backend/ingestion/ingest_pgvector.py` reads supported files from the Full
Stack Open repository using `find_course_files()` and `make_document()`.
English source paths are selected using the existing `/en/` convention.

Each source document is identified by `(source_type, source_path)` and replaced
atomically:

1. Upsert and reactivate the document.
2. Delete its previous chunks, which cascades to embeddings.
3. Insert the new typed chunks.
4. Insert one embedding per chunk and embedding contract.
5. Commit the document replacement as one transaction.

An individual document failure rolls back that replacement. The corpus is not
one global transaction, but stale-source reconciliation is suppressed after
any preprocessing or database failure.

## Typed Chunk Contract

`backend/rag/chunking.py` produces `PreparedChunk` records with:

- deterministic UUIDv5 `chunk_id`
- sequential `chunk_index`
- SHA-256 `content_hash`
- half-open `char_start` and `char_end`
- `heading_path` breadcrumbs and `section_heading`
- meaningful `chunk_type`
- `chunker_version`
- source and diagnostic metadata

Chunk identity includes source type, canonical source path, chunker version,
heading path, content hash, and same-hash occurrence. Identical source and
configuration reproduce IDs and ordering; source renames or chunker-version
changes intentionally create new identities.

## Markdown Structure

`markdown-structure-v3` parses Markdown into heading, prose, list, table, and
fenced-code blocks before assembling chunks.

- ATX headings update hierarchical breadcrumbs outside code fences.
- Backtick and tilde fences are preserved.
- Unclosed fences receive a synthetic closing fence and diagnostics.
- Complete code blocks may exceed the preferred 1,000-character size up to the
  configured hard maximum.
- Code above the hard maximum is split by lines with balanced synthetic fences.
- Tables split by row and repeat their header.
- Lists split on item/line boundaries.
- Prose prefers paragraph, sentence, and whitespace boundaries before using
  overlapping character fallback.
- Tiny compatible prose chunks merge within the same section; meaningful tiny
  code and table chunks remain independent.

Synthetic fences and repeated table headers set metadata indicating rendered
content differs from the exact source slice. Stored offsets continue to point
into the original source.

## Persistence and Migrations

Migration `20260610_0011` adds nullable chunk-contract columns and a unique
constraint on `(document_id, chunk_index)`. The columns are nullable so existing
rows remain readable during rollout; fresh re-ingestion is required to populate
them.

Migration `20260610_0012` adds:

- non-null `rag_documents.is_active`, defaulting to `true`
- nullable `rag_documents.deleted_at`
- an activity index

Fresh ingestion after migration establishes the Phase 2 active corpus and
populates `markdown-structure-v3` metadata. Deployment preflight must check for
duplicates before applying `0011`; see `runbook.md`.

`rag_embeddings.embedding` remains `vector(384)` with an HNSW cosine index.
Embedding identity is the full contract:

- `embedding_provider`
- `embedding_model`
- `embedding_dimensions`

## Soft Deletion

Stale-source reconciliation is explicitly enabled with
`--reconcile-deletions`. It is scoped by `source_type` and `course_name` and
runs only after a non-empty, complete ingestion without preprocessing or
database failures.

Missing sources are soft-deactivated by reconciliation. During normal non-dry
ingestion, discovered sources that are empty, excluded, or produce no chunks
are targeted for the same soft deactivation:

- `is_active` becomes `false`
- `deleted_at` records the reconciliation time
- document, chunk, and embedding rows remain for audit/history

Reappearing sources are reactivated by the normal document upsert, which sets
`is_active=true` and clears `deleted_at`. Empty scans, dry runs, and partial or
failed ingestions cannot reconcile stale sources.

## Runtime Retrieval

`PgvectorRagRetrievalProvider` embeds the query, then delegates to
`RagService`. The repository filters by embedding provider, model, dimensions,
and `rag_documents.is_active IS TRUE` directly in the nearest-neighbor SQL
query, so inactive sources never enter the pgvector candidate set.

Pgvector retrieves up to:

```text
min(RAG_TOP_K * RAG_CANDIDATE_POOL_MULTIPLIER, RAG_MAX_CANDIDATES)
```

Candidates are conservatively deduplicated in rank order by:

- identical chunk ID
- identical non-empty content hash
- normalized exact content when a hash is unavailable
- at least 80% overlap of the shorter source range within the same document

Adjacent chunks remain eligible. The retained list is truncated to
`RAG_TOP_K`.
Settings validation requires all three values to be positive and
`RAG_TOP_K <= RAG_MAX_CANDIDATES`.

Provider events report candidate count, retained count, and suppression
reasons. Logged chunk metadata describes retained chunks and excludes chunk
content. Durable PostgreSQL retrieval traces are built from the final retained
result used by the prompt. Trace-sink failures are fail-open and do not discard
retrieval results.

Retrieval failures propagate to `LLMService`, which records
`rag.retrieve.failed`, substitutes empty context, and allows generation to
continue.

## Prompt Context

`backend/llm/prompts.py` wraps retained chunks in `<retrieved_context>`.
Source labels prefer:

```text
source path | heading > breadcrumb | useful chunk type
```

Plain prose and unknown type labels are omitted. Missing metadata degrades to a
numbered context block without failing prompt construction.

## Deferred Work

The following are intentionally outside Phase 2:

- retrieval reranking
- hybrid semantic and keyword retrieval
- neighbor expansion
- similarity thresholds
- citation UI
- AST-aware Python chunking
- notebook-specific chunking refinements
- corpus-level retrieval evaluation and regression datasets

Retrieval currently uses semantic cosine similarity only. Quality evaluation
remains qualitative until an evaluation set and acceptance thresholds are
defined.
