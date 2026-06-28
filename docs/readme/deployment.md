# Deployment

Deployment should keep build/start commands separate from data maintenance. Backend startup should only start the API server. Frontend builds should only build the static site. RAG ingestion is a manual operation.

## Backend Service

Expected production backend responsibilities:

- Run the FastAPI app from `backend.main:app`
- Connect to the production PostgreSQL database with `postgresql+asyncpg://`
- Apply Alembic migrations as part of the deployment process
- Use production Clerk secrets and authorized parties
- Keep backend-only secrets off the frontend static site
- Keep API docs disabled unless intentionally exposed

Typical app start command:

```bash
uv run uvicorn backend.main:app --host 0.0.0.0 --port "$PORT"
```

## Frontend Static Site

The frontend build runs from `frontend/`:

```bash
npm install
npm run build
```

Production frontend environment must include browser-safe values:

```env
VITE_CLERK_PUBLISHABLE_KEY=pk_live_...
VITE_API_BASE_URL=https://your-backend.example.com
```

Set `VITE_DEMO_ADMIN_LOGIN_ENABLED=true` only for intentional demos where the backend demo admin shortcut is also enabled.

## Database and RAG

Before deploying schema changes to an environment with valuable data, back up the database.

Migration checks:

```bash
uv run alembic heads
uv run alembic upgrade head
uv run alembic current
```

Run RAG ingestion manually when the corpus or RAG schema changes:

```bash
uv run python -m backend.ingestion.ingest_pgvector --fail-fast
```

Do not put ingestion commands in Render backend start commands or frontend build commands. Use the [RAG runbook](../../backend/docs/rag/runbook.md) for verification and troubleshooting.

## Render Notes

See [final_render_safety_reconciliation.md](../final_render_safety_reconciliation.md) for the Render safety checklist and final RAG defaults.

The existing deployment notes are also useful historical references:

- [deployment_checklist.md](../deployment_checklist.md)
- [deployment_stratedgy.md](../deployment_stratedgy.md)

## Post-Deployment Checks

Run at minimum:

```bash
curl -sS https://your-backend.example.com/health
```

Then verify:

- The frontend can call the backend without CORS errors.
- Clerk sign-in works with the production authorized parties.
- Admin and instructor routes enforce the expected roles.
- Chat requests can retrieve RAG context and receive LLM responses.
- RAG corpus counts match the expected deployment state.
