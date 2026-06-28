# Local Setup

## Prerequisites

- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- Docker and Docker Compose
- Node.js and npm
- A local `.env` copied from `.env.example`

## One-Command Development Startup

From the repository root:

```bash
cp .env.example .env
uv sync
cd frontend && npm install && cd ..
uv run python scripts/dev.py
```

`scripts/dev.py` starts the `postgres` service from `compose.yaml`, waits for the database port, applies Alembic migrations, starts Uvicorn on `http://127.0.0.1:8001`, and starts Vite on `http://localhost:5173`.

The helper expects Docker to already be running. If `POSTGRES_PORT` is changed for Docker Compose, export the same value in the shell before running the script so its PostgreSQL readiness check waits on the correct port.

## Manual Backend Setup

Install dependencies:

```bash
uv sync
```

Create a local environment file:

```bash
cp .env.example .env
```

Start PostgreSQL with pgvector:

```bash
docker compose up -d postgres
docker compose ps postgres
```

The Docker image is `pgvector/pgvector:0.8.2-pg18-trixie`. The `vector` extension is enabled from `docker/postgres/init` when the database volume is first created.

Apply migrations:

```bash
uv run alembic heads
uv run alembic upgrade head
uv run alembic current
```

The current migration head is `20260624_0016`.

Start the backend:

```bash
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

Smoke-test the backend:

```bash
curl -sS http://127.0.0.1:8001/health
```

Most API routes require authentication. FastAPI docs are disabled unless `API_DOCS_ENABLED=true` is set before backend startup.

## Manual Frontend Setup

The frontend app has its own focused setup notes in [`frontend/README.md`](../../frontend/README.md).

Common local commands:

```bash
cd frontend
npm install
npm run dev
```

Create `frontend/.env.local` for browser-safe frontend settings:

```env
VITE_CLERK_PUBLISHABLE_KEY=pk_test_...
VITE_API_BASE_URL=http://127.0.0.1:8001
```

The backend `.env` must allow the Vite origin:

```env
CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]
```

Restart Vite after changing `frontend/.env.local`. Restart Uvicorn after changing backend `.env` values.

## RAG Ingestion

RAG ingestion is a manual maintenance step, not a backend startup command and not a frontend build command.

Run ingestion after migrations when the pgvector corpus needs to be created or refreshed:

```bash
uv run python -m backend.ingestion.ingest_pgvector --fail-fast
```

Use stale-source reconciliation only when intentionally scanning a complete source set:

```bash
uv run python -m backend.ingestion.ingest_pgvector --fail-fast --reconcile-deletions
```

For expected counts, verification SQL, troubleshooting, and operational details, use the [RAG runbook](../../backend/docs/rag/runbook.md).
