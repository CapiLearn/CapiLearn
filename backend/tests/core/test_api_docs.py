import pytest
from httpx import ASGITransport, AsyncClient

from backend.core.config import Settings
from backend.main import create_app


def test_api_docs_enabled_defaults_to_false() -> None:
    settings = Settings(_env_file=None)

    assert settings.api_docs_enabled is False


def test_api_docs_enabled_reads_env_var(monkeypatch) -> None:
    monkeypatch.setenv("API_DOCS_ENABLED", "true")

    settings = Settings(_env_file=None)

    assert settings.api_docs_enabled is True


@pytest.mark.asyncio
async def test_api_docs_are_disabled_by_default_without_disabling_health() -> None:
    app = create_app(Settings(_env_file=None))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            response = await client.get(path)

            assert response.status_code == 404

        response = await client.get("/health")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_api_docs_can_be_enabled() -> None:
    app = create_app(Settings(_env_file=None, api_docs_enabled=True))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            response = await client.get(path)

            assert response.status_code == 200
