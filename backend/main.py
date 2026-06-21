from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded

from backend.activity.router import router as activity_router
from backend.admin.router import router as admin_router
from backend.auth.router import router as auth_router
from backend.chat.router import router as chat_router
from backend.core.config import Settings, settings
from backend.core.exceptions import register_exception_handlers
from backend.core.observability import RequestIdMiddleware, configure_logging
from backend.core.rate_limiting import limiter, rate_limit_exceeded_handler
from backend.instructor.router import router as instructor_router
from backend.webhooks.router import router as webhook_router


def create_app(config: Settings | None = None) -> FastAPI:
    config = config or settings
    configure_logging(config)
    docs_url = "/docs" if config.api_docs_enabled else None
    redoc_url = "/redoc" if config.api_docs_enabled else None
    openapi_url = "/openapi.json" if config.api_docs_enabled else None
    app = FastAPI(
        title=config.app_name,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
    )
    register_exception_handlers(app)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_middleware(RequestIdMiddleware)

    if config.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=config.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(activity_router, prefix=config.api_prefix)
    app.include_router(chat_router, prefix=config.api_prefix)
    app.include_router(auth_router, prefix=config.api_prefix)
    app.include_router(admin_router, prefix=config.api_prefix)
    app.include_router(instructor_router, prefix=config.api_prefix)
    app.include_router(webhook_router, prefix=config.api_prefix)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
