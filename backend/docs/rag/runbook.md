# RAG Layer - Runbook

## Prerequisites

- Python 3.13 and project dependencies installed with `uv sync`
- Docker and Docker Compose
- Raw Full Stack Open repository at:
  `backend/ingestion/data/raw/fullstack-hy2020.github.io/`
- `DATABASE_URL` using `postgresql+asyncpg://`

No psycopg package is used.

## Prepare PostgreSQL

Start the pgvector-enabled database and apply migrations:

```bash
docker compose up -d postgres
uv run alembic heads
uv run alembic upgrade head
uv run alembic current
```

`uv run alembic heads` should report one head. `uv run alembic current` should
report that same revision after upgrade. The verified current revision is
`20260606_0005`.

## Ingest Course Content

Preview preprocessing without loading the embedding model or connecting to the
database:

```bash
uv run python -m backend.ingestion.ingest_pgvector --dry-run
```

Write documents, chunks, and embeddings:

```bash
uv run python -m backend.ingestion.ingest_pgvector
```

The command uses:

- `sentence-transformers/all-MiniLM-L6-v2`
- 384-dimensional embeddings
- 1,000-character chunks
- 200-character overlap
- English source paths only

For the current local corpus, a successful run writes approximately:

```text
72 documents
2,353 chunks
2,353 embeddings
```

Reruns replace each source document atomically, preventing duplicate chunks
for sources that still exist. Files removed from the source repository are not
automatically deleted from PostgreSQL.

Useful options:

```bash
uv run python -m backend.ingestion.ingest_pgvector --help
uv run python -m backend.ingestion.ingest_pgvector --fail-fast
uv run python -m backend.ingestion.ingest_pgvector --repo-path path/to/repo
```

## Enable pgvector Retrieval

Set these values in `.env`:

```dotenv
RAG_BACKEND=pgvector
RAG_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
RAG_TOP_K=5
RAG_WRITE_RETRIEVAL_LOGS=true
# RAG_INDEX_VERSION=full-stack-open-2026-06
```

The pgvector schema is fixed at `vector(384)`. The backend validates that
`RAG_MODEL_NAME` is `sentence-transformers/all-MiniLM-L6-v2` during startup,
and pgvector ingestion rejects any other model before loading it.

Restart FastAPI after changing RAG settings:

```bash
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

The query embedding runs in a worker thread. Similarity search uses async
SQLAlchemy and pgvector. Retrieved chunks are injected into the existing chat
prompt after input guardrails pass.

## Local Verification Checklist

1. Start PostgreSQL and confirm it is healthy:

   ```bash
   docker compose up -d postgres
   docker compose ps postgres
   ```

2. Apply migrations and confirm current/head alignment:

   ```bash
   uv run alembic upgrade head
   uv run alembic current
   uv run alembic heads
   ```

3. Ingest the corpus:

   ```bash
   uv run python -m backend.ingestion.ingest_pgvector
   ```

4. Check the stored records:

   ```bash
   docker compose exec postgres psql -U capilearn -d capilearn -c \
     "SELECT 'rag_documents' AS table_name, COUNT(*) FROM rag_documents
      UNION ALL SELECT 'rag_chunks', COUNT(*) FROM rag_chunks
      UNION ALL SELECT 'rag_embeddings', COUNT(*) FROM rag_embeddings
      UNION ALL SELECT 'rag_retrieval_logs', COUNT(*) FROM rag_retrieval_logs;"
   ```

   For the current corpus, the expected ingestion counts are 72 documents,
   2,353 chunks, and 2,353 embeddings. Retrieval logs may initially be zero.

5. Ensure `.env` selects pgvector before application startup:

   ```dotenv
   RAG_BACKEND=pgvector
   RAG_WRITE_RETRIEVAL_LOGS=true
   ```

6. Start FastAPI:

   ```bash
   uv run uvicorn backend.main:app --host 127.0.0.1 --port 8001
   ```

7. In another terminal, create a chat turn:

   ```bash
   curl -i -X POST http://127.0.0.1:8001/api/conversations \
     -H "Content-Type: application/json" \
     -d '{"content":"What is React state, and why would a component use it?"}'
   ```

8. Verify the latest retrieval:

   ```bash
   docker compose exec postgres psql -U capilearn -d capilearn -c \
     "SELECT query_text,
             json_array_length(retrieved_chunk_ids) AS chunk_count,
             scores
      FROM rag_retrieval_logs
      ORDER BY created_at DESC
      LIMIT 1;"
   ```

Successful runtime logs include:

- `rag.provider.retrieve.completed` with `backend=pgvector`
- a `chunk_count` greater than zero
- source paths, distances, and similarities
- `rag.retrieve.completed` when `LLMService` accepts retrieved chunks
- `llm.generation.completed` when the external LLM is available

The retrieved chunks are passed to `build_messages()`, which wraps them in the
existing `<retrieved_context>` prompt block. Retrieval failures degrade to
empty context at the LLM service retrieval boundary and log `rag.retrieve.failed`
without a matching `rag.retrieve.completed` event for that retrieval.

## Roll Back To Chroma

Set:

```dotenv
RAG_BACKEND=chroma
```

Restart FastAPI. The legacy Chroma files and local vector store remain
available, so rollback does not require deleting PostgreSQL data. The Chroma
query engine owns text-query embedding and collection lookup; the runtime
provider adapts that sync engine to the async retrieval protocol.

If the Chroma store must be rebuilt:

```bash
uv run python backend/ingestion/ingest_repo.py
uv run python backend/rag/chunk_documents.py
uv run python backend/rag/build_chroma_vector_store.py
```

## Troubleshooting

### Missing pgvector Extension

Symptoms include `type "vector" does not exist` or failures creating the HNSW
index.

Confirm the Docker image and extension:

```bash
docker compose up -d postgres
docker compose exec postgres psql -U capilearn -d capilearn \
  -c "SELECT extversion FROM pg_extension WHERE extname = 'vector';"
```

The initialization script runs `CREATE EXTENSION IF NOT EXISTS vector`.

### Empty RAG Tables

If retrieval returns no chunks, run the ingestion dry-run and then ingestion:

```bash
uv run python -m backend.ingestion.ingest_pgvector --dry-run
uv run python -m backend.ingestion.ingest_pgvector
```

Check that the write summary reports nonzero documents, chunks, and embeddings,
and verify `DATABASE_URL` points to the same database used by FastAPI.

### Embedding Dimension Mismatch

The database column is `vector(384)`. Both ingestion and retrieval must use
`sentence-transformers/all-MiniLM-L6-v2`, unless a future migration changes the
stored dimension. Any other pgvector model now fails configuration validation
instead of silently producing empty retrieval context.

Check:

```dotenv
RAG_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
```

Then reingest after correcting the model.

### Alembic Migration Issues

First inspect the graph and database revision:

```bash
uv run alembic heads
uv run alembic current
uv run alembic history --verbose
```

Do not blindly stamp a database that may be missing schema changes. If
`alembic current` references a revision absent from `alembic/versions`, inspect
the existing schema and recover the missing migration history before stamping.
For a disposable local database, recreating the Docker volume and running
`uv run alembic upgrade head` is usually the cleanest recovery.

For the known local-only stale-volume case where the database records
`20260527_0004`, stop Compose and remove only this project's disposable volume:

```bash
docker compose down
docker volume rm capilearn_postgres_data
docker compose up -d postgres
uv run alembic upgrade head
```

This deletes local database data. Do not use this procedure for a shared,
staging, or production database.

### RAG_BACKEND

Valid values are:

```dotenv
RAG_BACKEND=pgvector
RAG_BACKEND=chroma
```

Restart FastAPI after changing the value. Invalid values fail settings
validation during startup. Settings are cached in the application process, so
setting `RAG_BACKEND=pgvector` after Uvicorn has started does not switch the
running provider.

If the variable is omitted, the current code-level default is Chroma. The
branch's `.env.example` selects pgvector explicitly.

### Rejected OpenAI Key

An HTTP `503` with `AuthenticationError` after successful
`rag.provider.retrieve.completed` and `rag.retrieve.completed` events is an
external LLM credential or account issue, not a pgvector retrieval failure.

For the default OpenAI model, configure an active OpenAI Platform API key:

```dotenv
OPENAI_API_KEY=sk-...
LLM_MODEL=openai/gpt-4o-mini
```

Confirm the key belongs to an API project with available billing/credits, then
restart FastAPI. Do not place real keys in `.env.example` or commit `.env`.

### Embedding Model Download

The first model load may download files from Hugging Face. Use `--dry-run` when
you only need preprocessing counts.
