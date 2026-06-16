from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded

from backend.activity.router import router as activity_router
from backend.admin.router import router as admin_router
from backend.auth.router import router as auth_router
from backend.chat.router import router as chat_router
from backend.core.config import settings
from backend.core.exceptions import register_exception_handlers
from backend.core.observability import RequestIdMiddleware, configure_logging
from backend.core.rate_limiting import limiter, rate_limit_exceeded_handler


def create_app() -> FastAPI:
    configure_logging(settings)
    app = FastAPI(title=settings.app_name)
    register_exception_handlers(app)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_middleware(RequestIdMiddleware)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(activity_router, prefix=settings.api_prefix)
    app.include_router(chat_router, prefix=settings.api_prefix)
    app.include_router(auth_router, prefix=settings.api_prefix)
    app.include_router(admin_router, prefix=settings.api_prefix)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
