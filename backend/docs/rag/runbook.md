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
report that same revision after upgrade.

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

Restart FastAPI after changing RAG settings:

```bash
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

The query embedding runs in a worker thread. Similarity search uses async
SQLAlchemy and pgvector. Retrieved chunks are injected into the existing chat
prompt after input guardrails pass.

## Verify Data

The ingestion summary should show nonzero document, chunk, and embedding
counts. Retrieval logs should include:

- backend (`pgvector`)
- latency
- chunk count
- source path
- distance and similarity

Retrieval failures degrade to empty context and log `rag.retrieve.failed`.

## Roll Back To Chroma

Set:

```dotenv
RAG_BACKEND=chroma
```

Restart FastAPI. The legacy Chroma files and local vector store remain
available, so rollback does not require deleting PostgreSQL data.

If the Chroma store must be rebuilt:

```bash
uv run python backend/ingestion/ingest_repo.py
uv run python backend/rag/chunk_documents.py
uv run python backend/rag/build_vector_store.py
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
stored dimension.

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

### RAG_BACKEND

Valid values are:

```dotenv
RAG_BACKEND=pgvector
RAG_BACKEND=chroma
```

Restart FastAPI after changing the value. Invalid values fail settings
validation during startup.

### Embedding Model Download

The first model load may download files from Hugging Face. Use `--dry-run` when
you only need preprocessing counts.
