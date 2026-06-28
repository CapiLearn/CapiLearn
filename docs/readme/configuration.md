# Configuration

CapiLearn reads backend settings from `.env` through Pydantic settings. The frontend reads browser-safe Vite settings from `frontend/.env.local` during development and from deployment environment variables in production.

Start from:

```bash
cp .env.example .env
```

## Database

Local development uses PostgreSQL with pgvector from `compose.yaml`.

```env
POSTGRES_USER=capilearn
POSTGRES_PASSWORD=capilearn
POSTGRES_DB=capilearn
POSTGRES_PORT=55432
DATABASE_URL=postgresql+asyncpg://capilearn:capilearn@localhost:55432/capilearn
```

Use the `postgresql+asyncpg://` driver prefix. If `POSTGRES_PORT` changes, make the same port change in `DATABASE_URL`.

## CORS

The backend only installs CORS middleware when `CORS_ORIGINS` is configured. For local Vite development:

```env
CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]
```

Restart the backend after changing CORS settings.

## API Docs

FastAPI docs and OpenAPI routes are disabled by default:

```env
API_DOCS_ENABLED=false
```

Set `API_DOCS_ENABLED=true` for local debugging when `/docs`, `/redoc`, or `/openapi.json` are needed. Keep production API docs disabled unless there is an explicit reason to expose them.

## Authentication

The backend defaults to Clerk authentication:

```env
AUTH_MODE=clerk
CLERK_SECRET_KEY=sk_test_...
CLERK_JWT_KEY="-----BEGIN PUBLIC KEY-----..."
CLERK_WEBHOOK_SIGNING_SECRET=whsec_...
CLERK_AUTHORIZED_PARTIES=["http://localhost:5173","http://127.0.0.1:5173"]
```

Do not expose backend secrets such as `CLERK_SECRET_KEY` or `CLERK_WEBHOOK_SIGNING_SECRET` to the Vite static site.

For local or automated test auth, use `AUTH_MODE=test` with the `TEST_AUTH_*` claims from `.env.example`.

## Frontend Environment

Create `frontend/.env.local`:

```env
VITE_CLERK_PUBLISHABLE_KEY=pk_test_...
VITE_API_BASE_URL=http://127.0.0.1:8001
```

Only `VITE_*` variables are exposed to the browser. The Clerk publishable key is therefore configured as `VITE_CLERK_PUBLISHABLE_KEY`, not as a backend Clerk setting. Production frontend builds must set `VITE_CLERK_PUBLISHABLE_KEY` and `VITE_API_BASE_URL`.

## Demo Admin Login

The demo admin shortcut is disabled by default and requires both backend and frontend opt-in:

```env
DEMO_ADMIN_LOGIN_ENABLED=true
DEMO_ADMIN_EMAIL=admin@example.com
VITE_DEMO_ADMIN_LOGIN_ENABLED=true
```

The frontend flag only displays the button. The backend must also be configured to create a Clerk sign-in token for the configured email.

## LLM Provider

OpenAI through LiteLLM:

```env
OPENAI_API_KEY=sk-...
LLM_MODEL=openai/gpt-4o-mini
```

OpenRouter through LiteLLM:

```env
OPENROUTER_API_KEY=...
LLM_MODEL=openrouter/openai/gpt-4o-mini
LLM_GUARDRAILS_ENABLED=true
LLM_INPUT_GUARDRAIL_MODE=policy
LLM_OUTPUT_GUARDRAIL_MODE=policy
LLM_GUARDRAILS_JUDGE_MODEL=openrouter/openai/gpt-4o-mini
```

Use the `openrouter/` model prefix for OpenRouter-routed models.

## RAG Defaults

The current default RAG path is pgvector with OpenAI embeddings:

```env
RAG_BACKEND=pgvector
RAG_EMBEDDING_PROVIDER=openai
RAG_MODEL_NAME=text-embedding-3-small
RAG_EMBEDDING_DIMENSIONS=384
RAG_TOP_K=5
RAG_CANDIDATE_POOL_MULTIPLIER=3
RAG_MAX_CANDIDATES=50
RAG_WRITE_RETRIEVAL_LOGS=false
```

`RAG_BACKEND=chroma` is no longer supported for the app runtime. Restart the backend after changing RAG settings.

## Observability

Default local observability settings:

```env
LOG_LEVEL=INFO
LOG_FORMAT=json
REQUEST_ID_HEADER=X-Request-Id
OBSERVABILITY_ENABLED=true
OBSERVABILITY_CAPTURE_CONTENT=false
```

Keep `OBSERVABILITY_CAPTURE_CONTENT=false` unless intentionally debugging request or model content.
