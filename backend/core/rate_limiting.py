"""Per-user rate limiting primitives for API routes."""

from fastapi import Request, status
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from backend.core.exceptions import ErrorResponse

CHAT_MESSAGE_RATE_LIMIT = "10/minute"
CHAT_MESSAGE_RATE_LIMIT_SCOPE = "chat_messages"
DEMO_ADMIN_LOGIN_RATE_LIMIT = "10/minute"
DEMO_ADMIN_LOGIN_RATE_LIMITED_MESSAGE = "Too many admin login attempts. Please wait and try again."
RATE_LIMITED_MESSAGE = "You can send up to 10 messages per minute. Please wait and try again."


def rate_limit_key(request: Request) -> str:
    """Return the authenticated user key used to scope route limits."""
    current_user = getattr(request.state, "current_user", None)
    user_id = getattr(current_user, "id", None)
    if user_id is None:
        raise RuntimeError("Rate-limited routes require request.state.current_user.id")
    return f"user:{user_id}"


def ip_rate_limit_key(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return f"ip:{forwarded_for.split(',', 1)[0].strip()}"

    if request.client is None:
        return "ip:unknown"
    return f"ip:{request.client.host}"


# memory:// is process-local. If the API runs with multiple workers or replicas,
# switch this limiter to shared storage such as Redis.
limiter = Limiter(
    key_func=rate_limit_key,
    storage_uri="memory://",
    strategy="moving-window",
)


async def rate_limit_exceeded_handler(
    _: Request,
    exc: RateLimitExceeded,
) -> JSONResponse:
    """Return the public error payload for exceeded rate limits."""
    message = str(exc.detail)
    limit = DEMO_ADMIN_LOGIN_RATE_LIMIT
    if message != DEMO_ADMIN_LOGIN_RATE_LIMITED_MESSAGE:
        limit = CHAT_MESSAGE_RATE_LIMIT

    if message == str(exc.limit.limit):
        message = RATE_LIMITED_MESSAGE

    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content=ErrorResponse(
            code="rate_limited",
            message=message,
            details={"limit": limit},
        ).model_dump(),
    )
