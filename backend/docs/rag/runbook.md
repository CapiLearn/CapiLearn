# RAG Layer - Runbook

## Prerequisites

- Python 3.13 and project dependencies installed with `uv sync`
- Docker and Docker Compose
- Raw Full Stack Open repository at
  `backend/ingestion/data/raw/fullstack-hy2020.github.io/`
- `DATABASE_URL` using `postgresql+asyncpg://`
- A database backup or snapshot before production schema changes

PostgreSQL uses pgvector with 384-dimensional
`sentence-transformers/all-MiniLM-L6-v2` embeddings. No psycopg package is
used.

## Phase 2 Deployment Order

1. Confirm the release contains the complete Phase 2 implementation,
   migrations, tests, and documentation.
2. Back up the target database when it contains data that cannot be recreated.
3. Run the duplicate preflight SQL below before migration `20260610_0011`.
4. Confirm one Alembic head, then upgrade to `20260613_0013`.
5. Run a fresh pgvector ingestion. Re-ingestion is required because migration
   `0011` deliberately adds nullable fields without backfilling chunk content.
6. Run the post-ingestion SQL checks and confirm the expected active corpus.
7. Enable `--reconcile-deletions` only for an intentional, complete source
   scan.
8. Smoke-test retrieval and confirm inactive documents are excluded.

## Required Commands

Start PostgreSQL and check its health:

```bash
docker compose up -d postgres
docker compose ps postgres
```

Inspect and apply migrations:

```bash
uv run alembic heads
uv run alembic current
uv run alembic upgrade head
uv run alembic current
uv run alembic check
```

The single current head after upgrade must be `20260613_0013`.

Preview ingestion without loading the model or opening PostgreSQL:

```bash
uv run python -m backend.ingestion.ingest_pgvector --dry-run --fail-fast
```

Run a fresh ingestion without stale-source reconciliation:

```bash
uv run python -m backend.ingestion.ingest_pgvector --fail-fast
```

Run ingestion with intentional stale-source reconciliation:

```bash
uv run python -m backend.ingestion.ingest_pgvector --fail-fast --reconcile-deletions
```

Run release validation:

```bash
uv run pytest backend/tests
uv run ruff check backend
uv run ruff format --check backend
git diff --check
```

Useful ingestion options are listed by:

```bash
uv run python -m backend.ingestion.ingest_pgvector --help
```

## Duplicate Preflight Before Migration 0011

Migration `20260610_0011` adds unique constraints for chunk order and embedding
model identity. Migration `20260609_0010` establishes document source
identity. Run all three checks before upgrading a populated database. Each
query must return zero rows.

```sql
SELECT source_type, source_path, COUNT(*) AS duplicate_count
FROM rag_documents
GROUP BY source_type, source_path
HAVING COUNT(*) > 1;
```

```sql
SELECT document_id, chunk_index, COUNT(*) AS duplicate_count
FROM rag_chunks
GROUP BY document_id, chunk_index
HAVING COUNT(*) > 1;
```

```sql
SELECT chunk_id, embedding_model, COUNT(*) AS duplicate_count
FROM rag_embeddings
GROUP BY chunk_id, embedding_model
HAVING COUNT(*) > 1;
```

Do not apply `0011` until duplicates are understood and resolved through an
environment-specific data repair or fresh ingestion plan.

## Ingestion Contract

The Phase 2 ingestion path uses:

- `markdown-structure-v3`
- 1,000-character preferred chunks with 200-character overlap
- balanced fenced-code preservation and an explicit oversized-code policy
- deterministic UUIDv5 chunk IDs
- SHA-256 chunk content hashes
- half-open `char_start` / `char_end` offsets
- heading breadcrumbs, section headings, and meaningful chunk types
- atomic replacement of each document's chunks and embeddings

For the current Full Stack Open corpus, a fresh verified run produces:

```text
72 active documents
4,274 active chunks
4,274 active embeddings
0 ingestion failures
```

Counts may change when source content or chunker semantics change. Record such
changes in `metrics.md` and increment `CHUNKER_VERSION` when output semantics
change.

## Post-Ingestion Verification SQL

### Corpus Counts

```sql
SELECT
    COUNT(*) AS documents,
    COUNT(*) FILTER (WHERE is_active) AS active_documents,
    COUNT(*) FILTER (WHERE NOT is_active) AS inactive_documents
FROM rag_documents;

SELECT COUNT(*) AS active_chunks
FROM rag_chunks c
JOIN rag_documents d ON d.id = c.document_id
WHERE d.is_active IS TRUE;

SELECT COUNT(*) AS active_embeddings
FROM rag_embeddings e
JOIN rag_chunks c ON c.id = e.chunk_id
JOIN rag_documents d ON d.id = c.document_id
WHERE d.is_active IS TRUE;
```

### Version and Contract Population

```sql
SELECT chunker_version, COUNT(*)
FROM rag_chunks c
JOIN rag_documents d ON d.id = c.document_id
WHERE d.is_active IS TRUE
GROUP BY chunker_version
ORDER BY chunker_version;

SELECT
    COUNT(*) FILTER (WHERE c.content_hash IS NULL) AS content_hash_nulls,
    COUNT(*) FILTER (WHERE c.char_start IS NULL) AS char_start_nulls,
    COUNT(*) FILTER (WHERE c.char_end IS NULL) AS char_end_nulls,
    COUNT(*) FILTER (WHERE c.heading_path IS NULL) AS heading_path_nulls,
    COUNT(*) FILTER (WHERE c.chunk_type IS NULL) AS chunk_type_nulls,
    COUNT(*) FILTER (WHERE c.chunker_version IS NULL) AS chunker_version_nulls
FROM rag_chunks c
JOIN rag_documents d ON d.id = c.document_id
WHERE d.is_active IS TRUE;

SELECT COUNT(*) AS invalid_offsets
FROM rag_chunks c
JOIN rag_documents d ON d.id = c.document_id
WHERE d.is_active IS TRUE
  AND (c.char_start < 0 OR c.char_end <= c.char_start);

SELECT COUNT(*) AS invalid_hash_lengths
FROM rag_chunks c
JOIN rag_documents d ON d.id = c.document_id
WHERE d.is_active IS TRUE
  AND LENGTH(c.content_hash) <> 64;
```

Null `section_heading` values are valid only before any detected heading:

```sql
SELECT COUNT(*) AS invalid_null_section_headings
FROM rag_chunks c
JOIN rag_documents d ON d.id = c.document_id
WHERE d.is_active IS TRUE
  AND c.section_heading IS NULL
  AND c.heading_path::text <> '[]';
```

### Uniqueness and Orphans

The three duplicate queries from the preflight section must still return zero
rows. Also run:

```sql
SELECT c.id
FROM rag_chunks c
LEFT JOIN rag_documents d ON d.id = c.document_id
WHERE d.id IS NULL;

SELECT e.id
FROM rag_embeddings e
LEFT JOIN rag_chunks c ON c.id = e.chunk_id
WHERE c.id IS NULL;

SELECT c.id
FROM rag_chunks c
LEFT JOIN rag_embeddings e ON e.chunk_id = c.id
JOIN rag_documents d ON d.id = c.document_id
WHERE d.is_active IS TRUE
  AND e.id IS NULL;
```

Each orphan query must return zero rows.

### Activity State

```sql
SELECT
    COUNT(*) FILTER (WHERE NOT is_active AND deleted_at IS NULL)
        AS inactive_without_deleted_at,
    COUNT(*) FILTER (WHERE is_active AND deleted_at IS NOT NULL)
        AS active_with_deleted_at
FROM rag_documents;
```

Both values must be zero. The pgvector retrieval query includes
`rag_documents.is_active IS TRUE` beside the embedding-model filter. Confirm
the deployed code contains that predicate and perform a chat smoke test after
any reconciliation run.

## Soft Deletion and Reactivation

`rag_documents.is_active` controls retrieval eligibility and `deleted_at`
records when a source was deactivated. Soft deletion retains the document,
chunks, and embeddings for audit/history while excluding them from pgvector
retrieval.

Reconciliation is opt-in. It runs only when:

- `--reconcile-deletions` was provided
- the run is not a dry run
- at least one document and source path were discovered
- preprocessing completed without failure
- every database replacement completed without failure

It does not run after an empty, failed, partial, or dry-run ingestion. Its
scope is the configured `source_type` and `course_name`. A source that
reappears is reactivated automatically by the normal document upsert, which
sets `is_active=true` and clears `deleted_at`.

## Enable pgvector Retrieval

Set these values before application startup:

```dotenv
RAG_BACKEND=pgvector
RAG_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
RAG_TOP_K=5
RAG_WRITE_RETRIEVAL_LOGS=true
# RAG_INDEX_VERSION=full-stack-open-2026-06
```

Restart FastAPI after changing RAG settings:

```bash
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

Create a chat turn and inspect the latest durable retrieval record:

```bash
curl -i -X POST http://127.0.0.1:8001/api/conversations \
  -H "Content-Type: application/json" \
  -d '{"content":"What is React state, and why would a component use it?"}'

docker compose exec postgres psql -U capilearn -d capilearn -c \
  "SELECT query_text,
          json_array_length(retrieved_chunk_ids) AS chunk_count,
          scores
   FROM rag_retrieval_logs
   ORDER BY created_at DESC
   LIMIT 1;"
```

Expected events include `rag.provider.retrieve.completed` and
`rag.retrieve.completed`. Provider events distinguish raw candidate count,
retained count, and deduplication suppression reasons. Durable retrieval logs
contain the final retained chunks used by the prompt.

## Rollback

Application rollback must happen before schema downgrade.

1. Set `RAG_BACKEND=chroma` or deploy the previous application version.
2. Restart the backend and verify Chroma retrieval.
3. Leave the Phase 2 PostgreSQL schema and soft-deleted rows in place unless a
   separately approved rollback requires schema downgrade.
4. Only then consider `alembic downgrade`. Downgrading removes Phase 2 columns
   and constraints and must not occur while Phase 2 application code is live.

Inactive rows remain retained unless a later, explicit hard-deletion process
is approved. Switching to Chroma does not require deleting PostgreSQL data.

If the Chroma store must be rebuilt:

```bash
uv run python backend/ingestion/ingest_repo.py
uv run python backend/rag/chunk_documents.py
uv run python backend/rag/build_chroma_vector_store.py
```

## Troubleshooting

### Missing pgvector Extension

```bash
docker compose exec postgres psql -U capilearn -d capilearn \
  -c "SELECT extversion FROM pg_extension WHERE extname = 'vector';"
```

The initialization script runs `CREATE EXTENSION IF NOT EXISTS vector`.

### Empty or Stale RAG Tables

Run a dry run, then a normal ingestion:

```bash
uv run python -m backend.ingestion.ingest_pgvector --dry-run --fail-fast
uv run python -m backend.ingestion.ingest_pgvector --fail-fast
```

Verify `DATABASE_URL` points to the database used by FastAPI. Do not enable
reconciliation while diagnosing incomplete source discovery.

### Embedding Dimension Mismatch

The pgvector schema stores `vector(384)`. Both ingestion and retrieval must use
`sentence-transformers/all-MiniLM-L6-v2`; unsupported pgvector models fail
configuration validation.

### Alembic Migration Issues

```bash
uv run alembic heads
uv run alembic current
uv run alembic history --verbose
uv run alembic check
```

Do not blindly stamp a database that may be missing schema changes. Never use a
destructive volume reset for shared, staging, or production data.

### Backend Selection

Valid values are `RAG_BACKEND=pgvector` and `RAG_BACKEND=chroma`. Settings are
cached at startup, so restart FastAPI after changing the value.

### Downstream LLM Failure

An external LLM authentication or billing failure after successful
`rag.provider.retrieve.completed` and `rag.retrieve.completed` events is not a
pgvector retrieval failure.

### Embedding Model Download

The first model load may download files from Hugging Face. Use `--dry-run` when
only preprocessing counts are needed.
