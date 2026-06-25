"""Request-scoped context values for observability."""

from contextvars import ContextVar, Token
from uuid import uuid4

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def new_request_id() -> str:
    """Create a compact opaque request identifier."""
    return uuid4().hex


def get_request_id() -> str | None:
    """Return the request id bound to the current async context, if any."""
    return _request_id.get()


def set_request_id(request_id: str) -> Token[str | None]:
    """Bind a request id to the current async context."""
    return _request_id.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    """Restore the request id context to a previous token."""
    _request_id.reset(token)
