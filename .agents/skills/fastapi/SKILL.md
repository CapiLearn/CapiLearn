---
name: fastapi
description: Use when building, reviewing, or refactoring this repo's FastAPI backend. Applies to route handlers, Pydantic schemas, dependencies, database access, Alembic migrations, auth, background work, tests, API docs, and backend project structure. This repo prefers production-oriented FastAPI practices.
metadata:
  author: local
  version: "1.0.0"
  sources:
    - https://github.com/zhanymkanov/fastapi-best-practices/blob/master/AGENTS.md
    - https://github.com/fastapi/fastapi/blob/master/fastapi/.agents/skills/fastapi/SKILL.md
---

# FastAPI Backend Practices

Use this skill for FastAPI work in this repo. It adapts production-oriented FastAPI conventions from `zhanymkanov/fastapi-best-practices` and folds in official FastAPI skill guidance.

When local code already has a clear convention, preserve it unless the user asks for a refactor.

## Compatibility Matrix

Prefer these versions or newer for new backend work:

| Dependency | Minimum | Rule |
| --- | --- | --- |
| Python | 3.11 | Use modern typing: `StrEnum`, `T \| None`, `list[T]`. |
| FastAPI | 0.115 | Use `Annotated[T, Depends(...)]` and current FastAPI patterns. |
| Pydantic | 2.7 | Use v2 APIs; avoid v1 serialization and config patterns. |
| pydantic-settings | 2.4 | Settings live in a separate package in Pydantic v2. |
| SQLAlchemy | 2.0 | Use async SQLAlchemy: `AsyncSession`, `async_sessionmaker`. |
| Alembic | 1.13 | Use async-aware migrations. |
| httpx | 0.27 | Use `ASGITransport` for in-process API tests. |
| PyJWT | 2.9 | Use PyJWT, not `python-jose`. |
| Ruff | 0.6 | Prefer Ruff for linting and formatting. |

## FastAPI Entrypoint and CLI

Use the FastAPI CLI when available:

```bash
fastapi dev
fastapi run
```

Once the app module is stable, add an entrypoint to `pyproject.toml`:

```toml
[tool.fastapi]
entrypoint = "app.main:app"
```

If the project is still a small prototype or cannot set an entrypoint yet, pass the app path explicitly:

```bash
fastapi dev app/main.py
```

## Project Structure

Organize non-trivial APIs by domain, not by file type. Use one package per bounded context:

```text
app/
  {domain}/
    router.py
    schemas.py
    models.py
    service.py
    dependencies.py
    config.py
    constants.py
    exceptions.py
    utils.py
  config.py
  models.py
  exceptions.py
  database.py
  main.py
```

File roles:

- `router.py`: HTTP endpoints and route metadata.
- `schemas.py`: Pydantic request and response models.
- `models.py`: SQLAlchemy ORM models.
- `service.py`: business logic and persistence orchestration.
- `dependencies.py`: request-scoped validation and dependency composition.
- `config.py`: domain-scoped `BaseSettings`.
- `constants.py`: constants, enums, and error codes.
- `exceptions.py`: domain-specific exceptions.
- `utils.py`: small helpers that do not deserve service ownership.

Cross-domain imports must be explicit:

```python
from app.auth import constants as auth_constants
from app.notifications import service as notification_service
from app.posts.constants import ErrorCode as PostsErrorCode
```

Avoid wildcard imports and deep cross-domain imports such as `from app.auth.service.user import ...`.

## Routes and Routers

- Keep route handlers thin. Delegate business logic to services and request validation to dependencies.
- Use one HTTP operation per function. Do not branch on request method inside one handler.
- Prefer `APIRouter(prefix=..., tags=[...])` over passing `prefix` and `tags` in `include_router()`.
- Apply route-wide dependencies at the router level with `dependencies=[Depends(...)]`.
- Prefer one clear public response type per route.
- Use a return type when the handler naturally returns that public type.
- Use `response_model=` when the implementation returns an ORM row, `dict`, or internal type that must be filtered.
- Do not return a Pydantic model and also set `response_model=` to the same model. That can duplicate validation and serialization.
- Avoid `ORJSONResponse` and `UJSONResponse` for normal JSON APIs. Prefer return types or response models and let Pydantic handle serialization.

Example:

```python
from fastapi import APIRouter, status

router = APIRouter(prefix="/items", tags=["items"])


@router.post(
    "",
    response_model=ItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an item",
    description="Creates an item owned by the authenticated user.",
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
    },
)
async def create_item(payload: ItemCreate, session: DbSession) -> ItemResponse:
    return await item_service.create_item(session, payload)
```

## Async Routes

Decision rule:

| Route does this | Use |
| --- | --- |
| Awaitable non-blocking I/O | `async def` |
| Blocking I/O with no async client | `def`, which FastAPI runs in a threadpool |
| Mix of async and sync work | `async def` plus `run_in_threadpool` for the blocking part |
| CPU-bound work over roughly 50 ms | Worker process such as Celery, RQ, or Arq |

Rules:

- Do not put blocking calls inside `async def`.
- Avoid `requests`, `time.sleep`, sync database drivers, sync SQLAlchemy sessions, and regular file I/O inside async handlers.
- Use `httpx.AsyncClient` for async HTTP calls.
- Use `asyncio.sleep`, async database drivers, and async file helpers when needed.
- Use `fastapi.concurrency.run_in_threadpool` when an async route must call a sync SDK.
- Do not use sync routes just because they are easy. Starlette's default threadpool has limited capacity, and saturation slows every sync route.

Example:

```python
from fastapi.concurrency import run_in_threadpool


@router.get("/external/{item_id}")
async def fetch_external_item(item_id: str) -> ExternalItem:
    result = await run_in_threadpool(legacy_sync_client.fetch, item_id)
    return ExternalItem.model_validate(result)
```

## Pydantic

Use Pydantic v2 APIs and built-in validators:

```python
from enum import StrEnum

from pydantic import AnyUrl, BaseModel, EmailStr, Field


class MusicBand(StrEnum):
    AEROSMITH = "AEROSMITH"
    QUEEN = "QUEEN"
    ACDC = "AC/DC"


class UserCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=128)
    username: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    email: EmailStr
    age: int = Field(ge=18)
    favorite_band: MusicBand | None = None
    website: AnyUrl | None = None
```

Rules:

- Use `model_validate`, `model_dump`, `ConfigDict`, `field_serializer`, and `PlainSerializer`.
- Do not use deprecated v1 patterns: `.dict()`, `json_encoders`, or class-based `Config`.
- Do not use `...` for required Pydantic fields or FastAPI parameters. A field without a default is required.
- Do not write contradictory defaults such as `age: int = Field(default=None, ge=18)`.
- Use either `age: int = Field(ge=18)` or `age: int | None = Field(default=None, ge=18)`.
- Avoid `RootModel` for FastAPI request bodies when `Annotated` plus validation metadata can express the shape directly.

Modern serialization:

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, field_serializer


class CustomModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    @field_serializer("*", when_used="json", check_fields=False)
    def serialize_datetimes(self, value: object) -> object:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=ZoneInfo("UTC"))
            return value.strftime("%Y-%m-%dT%H:%M:%S%z")
        return value
```

Use `pydantic-settings` and split settings by domain:

```python
from datetime import timedelta

from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTH_", env_file=".env", extra="ignore")

    JWT_ALG: str
    JWT_SECRET: str
    JWT_EXP_MINUTES: int = 5
    REFRESH_TOKEN_KEY: str
    REFRESH_TOKEN_EXP: timedelta = timedelta(days=30)
    SECURE_COOKIES: bool = True


auth_settings = AuthConfig()
```

## Dependencies

Always prefer `Annotated`, not default-argument `Depends(...)`:

```python
from typing import Annotated

from fastapi import Depends

PostDep = Annotated[dict, Depends(valid_post_id)]


@router.get("/posts/{post_id}")
async def get_post(post: PostDep) -> dict:
    return post
```

Prefer reusable aliases for dependencies unless the user asks otherwise.

Validate inside dependencies, not just inject:

```python
async def valid_post_id(post_id: UUID4, session: DbSession) -> Post:
    post = await post_service.get_by_id(session, post_id)
    if post is None:
        raise PostNotFound()
    return post
```

Chain dependencies for reusable authorization checks:

```python
async def valid_owned_post(
    post: Annotated[Post, Depends(valid_post_id)],
    token_data: Annotated[TokenData, Depends(parse_jwt_data)],
) -> Post:
    if post.creator_id != token_data.user_id:
        raise UserNotOwner()
    return post
```

Rules:

- Dependencies are cached per request. The same dependency function runs once per request even if used multiple times.
- Prefer `async def` dependencies. Sync dependencies use the threadpool, which is overhead for small CPU-only checks.
- Use the same path variable name across endpoints when sharing a dependency.
- Use dependencies when logic needs external resources, cleanup with `yield`, request-scoped database validation, authorization checks, or reuse across endpoints.

## Authentication and JWT

Use PyJWT, not `python-jose`:

```python
import jwt
from jwt.exceptions import InvalidTokenError


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
    except InvalidTokenError as exc:
        raise InvalidCredentials() from exc
```

Rules:

- Catch specific auth exceptions.
- Do not catch broad `Exception` around route bodies.
- Do not expose token payloads directly as public response models.
- Map domain auth failures to meaningful HTTP responses.

## Database: SQLAlchemy 2.0 Async

Use SQLAlchemy 2.0 async as this repo's database default. Do not introduce SQLModel, `encode/databases`, sync SQLAlchemy sessions, or sync drivers unless the user explicitly changes the architecture.

```python
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

engine = create_async_engine(str(settings.DATABASE_URL), pool_pre_ping=True)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session
```

Prefer an alias for route injection:

```python
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

DbSession = Annotated[AsyncSession, Depends(get_db)]
```

Naming conventions:

- Use `lower_case_snake`.
- Prefer singular table names: `post`, `user`, `post_like`.
- Group related tables with prefixes: `payment_account`, `payment_bill`.
- Use `_at` for `datetime` columns and `_date` for `date` columns.
- Use the same foreign-key column name everywhere it appears.

Configure metadata naming conventions before migrations:

```python
from sqlalchemy import MetaData

POSTGRES_INDEXES_NAMING_CONVENTION = {
    "ix": "%(column_0_label)s_idx",
    "uq": "%(table_name)s_%(column_0_name)s_key",
    "ck": "%(table_name)s_%(constraint_name)s_check",
    "fk": "%(table_name)s_%(column_0_name)s_fkey",
    "pk": "%(table_name)s_pkey",
}

metadata = MetaData(naming_convention=POSTGRES_INDEXES_NAMING_CONVENTION)
```

SQL-first, Pydantic-second:

- Do joins, filtering, aggregation, sorting, and JSON shaping in SQL when practical.
- Hydrate results into Pydantic for response validation and serialization, not as a replacement for SQL.
- Keep commits at the service or unit-of-work boundary. Avoid hidden commits in low-level helpers.

## Background Work

| Use `BackgroundTasks` when | Use Celery, Arq, or RQ when |
| --- | --- |
| Task is under roughly 1 second | Task takes seconds to minutes |
| Failure can be silently dropped | Retries or dead-letter behavior matter |
| Task is in-process | Task is CPU-heavy or needs a separate pool |
| No scheduling is needed | Cron, ETA, or rate limiting is needed |

`BackgroundTasks` run after the response is sent in the same worker process. If the worker dies, the task is lost. Do not use them for anything that should page someone.

## Testing

Use async API tests from the start:

```python
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_create_post(client: AsyncClient) -> None:
    response = await client.post("/posts", json={"title": "hi"})
    assert response.status_code == 201
```

Rules:

- Use `httpx.AsyncClient` and `ASGITransport`.
- Do not use `async_asgi_testclient`.
- Use `app.dependency_overrides` for FastAPI dependencies.
- Do not monkeypatch route internals when dependency overrides are available.
- Prefer a real database for integration tests when SQL behavior matters. Use testcontainers, ephemeral schemas, or another isolated real database strategy.
- Mock external services at dependency boundaries.

Example dependency override:

```python
from collections.abc import Iterator

import pytest

from app.auth.dependencies import parse_jwt_data
from app.main import app


def fake_user() -> dict:
    return {"user_id": "00000000-0000-0000-0000-000000000001"}


@pytest.fixture(autouse=True)
def override_auth() -> Iterator[None]:
    app.dependency_overrides[parse_jwt_data] = fake_user
    yield
    app.dependency_overrides.clear()
```

## Migrations

Use Alembic for schema changes:

- Migrations must be static, deterministic, reviewable, and reversible.
- Use the async template: `alembic init -t async migrations`.
- Do not depend on application runtime state or external services during migration execution.
- Use descriptive filenames.

Recommended `alembic.ini` filename template:

```ini
file_template = %%(year)d-%%(month).2d-%%(day).2d_%%(slug)s
```

## API Documentation

Hide docs outside selected environments when public docs are not intended:

```python
from fastapi import FastAPI

from app.config import settings

SHOW_DOCS_IN = {"local", "staging"}

app_kwargs = {"title": "My API"}
if settings.ENVIRONMENT not in SHOW_DOCS_IN:
    app_kwargs["openapi_url"] = None

app = FastAPI(**app_kwargs)
```

Document public endpoints with route metadata, explicit status codes, and expected error responses.

## Streaming

Use FastAPI and Starlette streaming primitives intentionally:

- Use `StreamingResponse` for byte or chunk streams.
- Use Server-Sent Events libraries for SSE instead of hand-rolled response loops.
- Use JSON Lines when each event is independent and clients can process partial results.
- Do not buffer an entire stream in memory before returning it.

## Linting

Use Ruff unless the repo already has a stronger local standard:

```bash
ruff check --fix app
ruff format app
```

Run linting and formatting in CI once backend code exists.

## Anti-Patterns

When reviewing a diff, check for these:

| Anti-pattern | Why it is wrong | Fix |
| --- | --- | --- |
| `requests.get(...)` inside `async def` | Blocks the event loop. | Use `httpx.AsyncClient` or `run_in_threadpool`. |
| `time.sleep`, `open`, or sync DB calls inside `async def` | Blocks the event loop. | Use async equivalents or isolate in a threadpool. |
| `from jose import jwt` | `python-jose` is unmaintained. | Use PyJWT: `import jwt`. |
| `async_asgi_testclient` | Unmaintained test client. | Use `httpx.AsyncClient` and `ASGITransport`. |
| `ConfigDict(json_encoders={...})` | Deprecated Pydantic v2 pattern. | Use `field_serializer` or `PlainSerializer`. |
| `Field(ge=18, default=None)` | Constraint and default contradict each other. | Pick required or optional. |
| `user: User = Depends(...)` | Legacy default-argument dependency style. | Use `Annotated[User, Depends(...)]`. |
| Broad `except Exception` in route bodies | Hides bugs and can mask 500s. | Catch specific exceptions. |
| `BackgroundTasks` for critical work | No retry or durability. | Use Celery, Arq, or RQ. |
| Sync ORM session in async code | Blocks the loop and can deadlock pools. | Use `AsyncSession`. |
| Returning a model and duplicating `response_model` | Duplicates validation and serialization. | Use either return typing or `response_model` intentionally. |
| Deep cross-domain imports | Tight coupling and hard refactors. | Import explicit domain modules. |
| One global `BaseSettings` for everything | Every domain reads every variable. | Use domain-scoped settings. |
| Mocking DB behavior in integration tests | Diverges from production SQL behavior. | Use an isolated real database. |
| Multiple HTTP methods in one handler | Mixes concerns and complicates docs. | Use one operation function per method. |
| Pydantic `RootModel` for simple request bodies | Adds unnecessary custom wrapper types. | Use `Annotated[list[T], Field(...), Body()]`. |

## Quick Reference

| Scenario | Solution |
| --- | --- |
| Non-blocking I/O | `async def` route with `await` |
| Blocking I/O with no async client | `def` route |
| Sync SDK inside async route | `await run_in_threadpool(fn, *args)` |
| CPU-intensive work | Worker process |
| Request validation against DB | Dependency that loads, validates, and returns |
| Reuse validation across routes | Chain dependencies |
| Inject dependency | `Annotated[T, Depends(...)]` |
| Per-request dependency caching | Default FastAPI behavior |
| Per-domain config | One `BaseSettings` subclass per domain |
| Custom datetime serialization | `field_serializer` |
| Short best-effort side effect | `BackgroundTasks` |
| Reliable scheduled or heavy task | Celery, Arq, or RQ |
| JWT decode | PyJWT |
| Async DB | SQLAlchemy 2.0 `AsyncSession` |
| API test client | `httpx.AsyncClient` and `ASGITransport` |
| Swap dependency in tests | `app.dependency_overrides[dep] = fake` |
| Lint and format | `ruff check --fix` and `ruff format` |
| Run FastAPI locally | `fastapi dev` |
| Production FastAPI command | `fastapi run` |
