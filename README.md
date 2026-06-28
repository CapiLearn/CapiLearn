# CapiLearn

CapiLearn is an AI-powered learning assistant that helps students work through problems instead of only receiving answers. The app combines a React browser client, a FastAPI backend, Clerk authentication, LiteLLM-backed model access, policy guardrails, and pgvector retrieval over course material.

## Team

- Elizabeth Howard
- Stephan Caamano
- Jose Diaz

## Tech Stack

- React and Vite frontend
- FastAPI backend on Python 3.13
- PostgreSQL with pgvector
- Alembic migrations
- Clerk authentication
- LiteLLM for LLM provider access
- In-repo RAG, ingestion, and policy guardrails

## Quick Start

Prerequisites:

- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- Docker and Docker Compose
- Node.js and npm

Start the local stack:

```bash
cp .env.example .env
uv sync
cd frontend && npm install && cd ..
uv run python scripts/dev.py
```

The helper starts PostgreSQL, applies migrations, and runs both dev servers:

- Backend: `http://127.0.0.1:8001`
- Frontend: `http://localhost:5173`

FastAPI's `/docs` and `/openapi.json` routes are disabled by default. Set `API_DOCS_ENABLED=true` in `.env` and restart the backend when local API docs are needed.

## Documentation

Detailed project documentation lives in [`docs/readme`](docs/readme/README.md):

- [Local setup](docs/readme/setup.md)
- [Configuration](docs/readme/configuration.md)
- [Development commands](docs/readme/development.md)
- [Architecture](docs/readme/architecture.md)
- [Deployment](docs/readme/deployment.md)

Specialized documentation:

- [Frontend README](frontend/README.md)
- [Backend docs index](backend/docs/index.md)
- [RAG runbook](backend/docs/rag/runbook.md)
- [UI design specification](docs/UI_design_specification.md)
- [Credits and attribution](CREDITS.md)

## Architecture

![Architecture Diagram](docs/educational-ai-assistant-system-design-simplified.png)

See [docs/readme/architecture.md](docs/readme/architecture.md) for the current system overview and links to the RAG architecture notes.

## Ownership

- Jose: UI/UX and endpoints
- Stephan: LLM and guardrails
- Lizzie: RAG and ingestion
