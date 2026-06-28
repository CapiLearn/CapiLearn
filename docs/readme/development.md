# Development Commands

Run commands from the repository root unless noted otherwise.

## Backend

Install or sync Python dependencies:

```bash
uv sync
```

Run backend tests:

```bash
uv run pytest backend/tests
```

Run a narrower test area:

```bash
uv run pytest backend/tests/rag
uv run pytest backend/tests/chat
uv run pytest backend/tests/auth
```

Check formatting and linting:

```bash
uv run ruff check .
uv run ruff format --check .
```

Apply database migrations:

```bash
uv run alembic heads
uv run alembic upgrade head
uv run alembic current
```

Generate a migration after SQLAlchemy model changes:

```bash
uv run alembic revision --autogenerate -m "Describe schema change"
uv run alembic upgrade head
uv run alembic check
```

The current migration head is `20260624_0016`.

## Frontend

Run from `frontend/`:

```bash
npm install
npm run dev
npm run lint
npm run test
npm run build
```

See [`frontend/README.md`](../../frontend/README.md) for frontend-specific environment notes.

## Local Stack

Start PostgreSQL:

```bash
docker compose up -d postgres
docker compose ps postgres
```

Start backend and frontend together:

```bash
uv run python scripts/dev.py
```

Start backend manually:

```bash
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

Start frontend manually:

```bash
cd frontend
npm run dev
```

## Smoke Tests

Backend health:

```bash
curl -sS http://127.0.0.1:8001/health
```

Authenticated API calls require a valid Clerk session token, except when the backend is intentionally running in `AUTH_MODE=test`.

## RAG Maintenance

Preview ingestion:

```bash
uv run python -m backend.ingestion.ingest_pgvector --dry-run --fail-fast
```

Run ingestion:

```bash
uv run python -m backend.ingestion.ingest_pgvector --fail-fast
```

Show ingestion options:

```bash
uv run python -m backend.ingestion.ingest_pgvector --help
```

Use the [RAG runbook](../../backend/docs/rag/runbook.md) for verification SQL, expected corpus counts, and troubleshooting.
