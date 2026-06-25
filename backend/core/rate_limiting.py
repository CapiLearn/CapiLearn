"""Per-user rate limiting primitives for API routes."""

from fastapi import Request, status
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from backend.core.exceptions import ErrorResponse

CHAT_MESSAGE_RATE_LIMIT = "10/minute"
CHAT_MESSAGE_RATE_LIMIT_SCOPE = "chat_messages"
RATE_LIMITED_MESSAGE = "You can send up to 10 messages per minute. Please wait and try again."


def rate_limit_key(request: Request) -> str:
    """Return the authenticated user key used to scope route limits."""
    current_user = getattr(request.state, "current_user", None)
    user_id = getattr(current_user, "id", None)
    if user_id is None:
        raise RuntimeError("Rate-limited routes require request.state.current_user.id")
    return f"user:{user_id}"


# memory:// is process-local. If the API runs with multiple workers or replicas,
# switch this limiter to shared storage such as Redis.
limiter = Limiter(
    key_func=rate_limit_key,
    storage_uri="memory://",
    strategy="moving-window",
)


async def rate_limit_exceeded_handler(
    _: Request,
    __: RateLimitExceeded,
) -> JSONResponse:
    """Return the public error payload for exceeded rate limits."""
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content=ErrorResponse(
            code="rate_limited",
            message=RATE_LIMITED_MESSAGE,
            details={"limit": CHAT_MESSAGE_RATE_LIMIT},
        ).model_dump(),
    )
