# CapiLearn Frontend

The frontend is a React application built with Vite.

## Environment

Set the backend API origin at build time:

```env
VITE_API_BASE_URL=http://127.0.0.1:8001
```

For Render, use the deployed FastAPI service URL, such as
`https://capilearn-api.onrender.com`. The client removes a trailing slash.
When the variable is absent, local development defaults to
`http://127.0.0.1:8001`.

## Commands

```bash
npm install
npm run dev
npm run lint
npm run build
```
