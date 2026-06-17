# Project Name: CapiLearn

# Team Members:

    ## Elizabeth Howard
    ## Stephan Caamano
    ## Jose Diaz

# Description:

CapiLearn is an AI-powered learning assistant designed to help students think through problems instead of just receiving answers. Using conversational AI and retrieval-based support, the platform guides users with Socratic-style questioning, personalized explanations, and contextual academic support.
The goal is to create a more engaging and ethical homework help experience that strengthens understanding, reduces dependency on answer-copying, and gives students a space to learn interactively and confidently.

# Tech Stack

    - React.js
    - python
    - LLM
    - in-repo policy guardrails
    - RAG
    - Postgres DB with VectorDB extension

# Branches

    -  UI
    -  endpoints
    -  LLM
    -  RAG
    -  DB
    -  guardrails
        - pre
        - post 
    - ingestion
    
# Folder structure

```
backend/
├── DB/
├── endpoints/
├── ingestion/
├── LLM/
├── RAG/
└── tests/
data/
docs/
frontend/
└── tests/
```

    

# Setup and Installation

## Prerequisites

- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- Docker and Docker Compose
- Node.js and npm for the frontend

## Backend Setup

1. Install Python dependencies:

    ```bash
    uv sync
    ```


2. Create a local environment file:

    ```bash
    cp .env.example .env
    ```

    The default local database URL is:

    ```bash
    postgresql+asyncpg://capilearn:capilearn@localhost:55432/capilearn
    ```

    If you already have a local `.env`, change the database URL prefix from
    `postgresql+psycopg://` to `postgresql+asyncpg://`.

    If port `55432` is already in use, set `POSTGRES_PORT` in `.env` and update
    the port in `DATABASE_URL` to match.

    If you already have a local `.env`, make sure it also allows the Vite
    frontend origin for browser requests:

    ```env
    CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]
    ```

    Restart Uvicorn after changing `CORS_ORIGINS`; the FastAPI settings are
    loaded when the server starts.

3. Configure LLM access in `.env`.

    For OpenAI directly through LiteLLM:

    ```env
    OPENAI_API_KEY=sk-...
    LLM_MODEL=openai/gpt-4o-mini
    ```

    An OpenAI API key requires active API billing or credits. A ChatGPT
    subscription alone does not provide API credits.

    For OpenRouter through LiteLLM, set `OPENROUTER_API_KEY` and prefix model
    names with `openrouter/`. The prefix tells LiteLLM to route the request
    through OpenRouter; without it, the model can be sent to the wrong provider
    or fail provider resolution.

    ```env
    OPENROUTER_API_KEY=...
    LLM_MODEL=openrouter/openai/gpt-4o-mini
    LLM_GUARDRAILS_ENABLED=true
    LLM_INPUT_GUARDRAIL_MODE=policy
    LLM_OUTPUT_GUARDRAIL_MODE=policy
    LLM_GUARDRAILS_JUDGE_MODEL=openrouter/openai/gpt-4o-mini
    ```

    Use the same `openrouter/` prefix for any other OpenRouter model, for
    example `openrouter/anthropic/claude-3.5-sonnet`.

4. Start Postgres with pgvector:

    ```bash
    docker compose up -d postgres
    ```

    The database image is `pgvector/pgvector:0.8.2-pg18-trixie`. The `vector`
    extension is enabled automatically from `docker/postgres/init` when the
    database volume is first created.

5. Run database migrations:

    ```bash
    uv run alembic heads
    uv run alembic upgrade head
    uv run alembic current
    ```

    The migration graph should have one head at `20260610_0008`. Phase 2
    migration `0007` adds nullable chunk-contract fields and uniqueness
    constraints; `0008` adds document activity fields. A fresh re-ingestion is
    required after upgrading so the active corpus uses the new metadata and
    `markdown-structure-v3` chunker.

6. Ingest the pgvector corpus:

    ```bash
    uv run python -m backend.ingestion.ingest_pgvector
    ```

    The current corpus should produce 72 active documents, 4,274 active chunks,
    and 4,274 active 384-dimensional embeddings. Stale-source reconciliation is
    intentionally opt-in:

    ```bash
    uv run python -m backend.ingestion.ingest_pgvector --fail-fast --reconcile-deletions
    ```

    Reconciliation retains stale documents with `is_active=false` and
    `deleted_at` populated; inactive documents are excluded from retrieval.
    See the RAG runbook before enabling this flag on a shared environment.

7. Confirm `.env` selects the preferred backend:

    ```env
    RAG_BACKEND=pgvector
    RAG_EMBEDDING_PROVIDER=openai
    RAG_MODEL_NAME=text-embedding-3-small
    RAG_EMBEDDING_DIMENSIONS=384
    RAG_WRITE_RETRIEVAL_LOGS=true
    ```

    `RAG_BACKEND=chroma` is no longer supported. Restart the backend whenever
    RAG settings change.

8. Start the FastAPI backend:

    ```bash
    uv run uvicorn backend.main:app --host 127.0.0.1 --port 8001
    ```

9. Smoke-test the backend:

    ```bash
    curl -sS http://127.0.0.1:8001/health
    curl -sS http://127.0.0.1:8001/api/conversations
    ```

    For the full pgvector verification checklist, SQL count queries, chat
    payload, and troubleshooting steps, see
    [`backend/docs/rag/runbook.md`](backend/docs/rag/runbook.md).

## Frontend Setup

1. Install frontend dependencies:

    ```bash
    cd frontend
    npm install
    ```

2. Start the Vite dev server:

    ```bash
    npm run dev
    ```

    The frontend runs on `http://localhost:5173` by default. That origin must be
    present in the backend `.env` `CORS_ORIGINS` value.

## Common Development Commands

Run backend tests:

```bash
uv run pytest backend/tests
```

Check backend formatting and linting:

```bash
uv run ruff check .
uv run ruff format --check .
```

Generate a future Alembic migration after SQLAlchemy model changes:

```bash
uv run alembic revision --autogenerate -m "Describe schema change"
uv run alembic upgrade head
uv run alembic check
```

Run frontend checks:

```bash
cd frontend
npm run lint
npm run build
```

# Architecture Diagram

![Architecture Diagram](docs/educational-ai-assistant-system-design-simplified.png)


# Ownership

    Jose - UI/UX, endpoints
    Stephan - LLM, guardrails
    Lizzie - RAG, ingestion
