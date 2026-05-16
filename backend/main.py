from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.chat.router import router as chat_router
from backend.core.config import settings
from backend.core.exceptions import register_exception_handlers


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)
    register_exception_handlers(app)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(chat_router, prefix=settings.api_prefix)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
