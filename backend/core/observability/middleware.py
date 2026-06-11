import logging
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from backend.core.config import settings
from backend.core.observability.context import (
    new_request_id,
    reset_request_id,
    set_request_id,
)
from backend.core.observability.logging import log_event
from backend.core.observability.timing import elapsed_ms, timer_start

logger = logging.getLogger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get(settings.request_id_header) or new_request_id()
        token = set_request_id(request_id)
        started_at = timer_start()
        log_event(
            logger,
            "http.request.started",
            method=request.method,
            path=request.url.path,
        )
        try:
            response = await call_next(request)
        except Exception as exc:
            log_event(
                logger,
                "http.request.failed",
                level=logging.ERROR,
                method=request.method,
                path=request.url.path,
                route=_route_path(request),
                latency_ms=elapsed_ms(started_at),
                exc_info=exc,
            )
            raise
        else:
            response.headers[settings.request_id_header] = request_id
            log_event(
                logger,
                "http.request.completed",
                method=request.method,
                path=request.url.path,
                route=_route_path(request),
                status_code=response.status_code,
                latency_ms=elapsed_ms(started_at),
            )
            return response
        finally:
            reset_request_id(token)


def _route_path(request: Request) -> str | None:
    route = request.scope.get("route")
    return getattr(route, "path", None)
