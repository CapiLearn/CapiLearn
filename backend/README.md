# Backend

## Development Setup

This backend uses `uv` for dependency management and Ruff for Python linting
and formatting.

Install dependencies from the backend directory:

```bash
cd backend
uv sync --dev
```

Run the same checks that CI runs:

```bash
uv run ruff format --check .
uv run ruff check .
```

Apply local fixes before committing:

```bash
uv run ruff format .
uv run ruff check --fix .
```

## Pre-Commit Hooks

The repository includes a root `.pre-commit-config.yaml` that runs Ruff against
backend Python files before commits.

Install the Git hooks from the repository root:

```bash
uvx pre-commit install
```

Run hooks across all files manually:

```bash
uvx pre-commit run --all-files
```

The hooks are a local convenience. GitHub Actions is the shared enforcement
point for pull requests and pushes to `main`.
