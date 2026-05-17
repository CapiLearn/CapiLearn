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
    postgresql+psycopg://capilearn:capilearn@localhost:5432/capilearn
    ```

    If port `5432` is already in use, set `POSTGRES_PORT` in `.env` and update
    the port in `DATABASE_URL` to match.

3. Configure LLM access in `.env`.

    For OpenRouter through LiteLLM, use the OpenRouter provider prefix:

    ```env
    OPENROUTER_API_KEY=...
    LLM_MODEL=openrouter/openai/gpt-4o-mini
    LLM_GUARDRAILS_ENABLED=true
    LLM_INPUT_GUARDRAIL_MODE=policy
    LLM_OUTPUT_GUARDRAIL_MODE=policy
    LLM_GUARDRAILS_JUDGE_MODEL=openrouter/openai/gpt-4o-mini
    ```

4. Start Postgres with pgvector:

    ```bash
    docker compose up -d postgres
    ```

    The database image is `pgvector/pgvector:0.8.2-pg18-trixie`. The `vector`
    extension is enabled automatically from `docker/postgres/init` when the
    database volume is first created.

5. Run database migrations:

    ```bash
    uv run alembic upgrade head
    uv run alembic current
    ```

    If you already created tables locally with the old manual Python command,
    stamp the database instead of rerunning the initial migration:

    ```bash
    uv run alembic stamp head
    ```

6. Start the FastAPI backend:

    ```bash
    uv run uvicorn backend.main:app --host 127.0.0.1 --port 8001
    ```

7. Smoke-test the backend:

    ```bash
    curl -sS http://127.0.0.1:8001/health
    curl -sS http://127.0.0.1:8001/api/conversations
    ```

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
    Lizzy - RAG, ingestion
