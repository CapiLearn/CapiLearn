# CapiLearn Frontend

This React/Vite app is the browser client for CapiLearn. It uses Clerk for
sign-in, calls the FastAPI backend through `VITE_API_BASE_URL`, and renders the
student workspace, dashboards, and demo-only admin login entry point.

## Local Setup

```bash
npm install
npm run dev
```

Create `frontend/.env.local` for local browser-safe values:

```env
VITE_CLERK_PUBLISHABLE_KEY=pk_test_...
VITE_API_BASE_URL=http://127.0.0.1:8001
```

Restart Vite after changing these values. Production Render builds must set
`VITE_CLERK_PUBLISHABLE_KEY` and `VITE_API_BASE_URL` on the frontend static
site.

## Demo Admin Login

`VITE_DEMO_ADMIN_LOGIN_ENABLED=true` only shows the frontend button. The backend
must also explicitly set `DEMO_ADMIN_LOGIN_ENABLED=true` and a
`DEMO_ADMIN_EMAIL`. Keep this disabled by default outside intentional demos.

## Checks

```bash
npm run lint
npm run build
```
