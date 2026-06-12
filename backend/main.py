from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.admin.router import router as admin_router
from backend.chat.router import router as chat_router
from backend.core.beta_auth import BetaAuthMiddleware
from backend.core.config import Settings, settings
from backend.core.exceptions import register_exception_handlers
from backend.core.observability import RequestIdMiddleware, configure_logging


def create_app(app_settings: Settings = settings) -> FastAPI:
    configure_logging(app_settings)
    app = FastAPI(title=app_settings.app_name)
    register_exception_handlers(app)

    if app_settings.beta_auth_enabled:
        app.add_middleware(
            BetaAuthMiddleware,
            username=app_settings.beta_auth_username.get_secret_value(),
            password=app_settings.beta_auth_password.get_secret_value(),
        )

    app.add_middleware(RequestIdMiddleware)

    if app_settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=app_settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(chat_router, prefix=app_settings.api_prefix)
    app.include_router(admin_router, prefix=app_settings.api_prefix)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
