"""Shared API exception types and FastAPI handlers."""

from typing import Any

from fastapi import Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Wire format returned for application-level API errors."""

    code: str
    message: str
    details: dict[str, Any] | None = None


class ApiError(Exception):
    """Application exception that maps directly to an HTTP JSON response."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    """Convert an ApiError raised by application code into JSON."""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            code=exc.code,
            message=exc.message,
            details=exc.details,
        ).model_dump(),
    )
