# Final Render Safety Reconciliation

## Purpose

This PR prepares current `main` to replace the previously deployed beta branch
on Render with minimal additional handoff review. It reconciles deploy-facing
configuration and docs with the validated beta Render behavior.

## Validated Beta Topology to Preserve

- Separate Render backend service.
- Separate Render frontend static site.
- Render Postgres.
- Validated beta backend URL: `https://capilearn.onrender.com`
- Validated beta frontend URL: `https://capilearn-1.onrender.com`
- Backend start command:
  `uv run uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
- Frontend root: `frontend`
- Frontend build: `npm ci && npm run build`
- Frontend publish directory: `dist`
- SPA rewrite: `/* -> /index.html`
- Frontend `VITE_API_BASE_URL` must point to the deployed backend service.

## Final Default RAG Config

```env
RAG_BACKEND=pgvector
RAG_EMBEDDING_PROVIDER=openai
RAG_MODEL_NAME=text-embedding-3-small
RAG_EMBEDDING_DIMENSIONS=384
RAG_WRITE_RETRIEVAL_LOGS=false
```

Keep `RAG_WRITE_RETRIEVAL_LOGS=false` as the deployment default unless it is
intentionally overridden for a specific verification or debugging window.

## Manual-Only Ingestion Rule

- Do not put ingestion commands in the Render backend start command.
- Do not put ingestion commands in the frontend build command.
- Empty-RAG deployment is acceptable when intentional.
- Run ingestion only after env/migration confirmation and explicit approval.

## Render Dashboard Verification Checklist

- [ ] Backend service branch/source points to the intended final branch or
      post-merge `main`.
- [ ] Frontend static site branch/source points to the intended final branch or
      post-merge `main`.
- [ ] Backend start command only starts the API server.
- [ ] Frontend root, build command, publish directory, and SPA rewrite match the
      validated beta settings above.
- [ ] Backend env includes the final/default RAG config above.
- [ ] Backend env includes valid `DATABASE_URL` and required LLM/OpenAI secrets.
- [ ] Backend env sets `API_DOCS_ENABLED=false` for production.
- [ ] Frontend env sets `VITE_API_BASE_URL` to the deployed backend URL.
- [ ] No Chroma or local `sentence-transformers` env values are configured for
      the Render deployment.
- [ ] No automatic ingestion command appears in backend startup or frontend
      build settings.
- [ ] Backend `/health` returns 200 after deploy.
- [ ] Browser network calls from the frontend go to the deployed backend, not
      `localhost` or `127.0.0.1`.

## Deferred Cleanup / Out of Scope

- Chroma runtime remnants, as long as validation rejects unsupported deploy
  config.
- Basic Auth or Clerk cleanup unless separately scoped.
- RAG ingestion quality and corpus population.
- Production-grade migration automation.
