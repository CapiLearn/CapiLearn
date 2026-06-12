import base64

import pytest
from httpx import ASGITransport, AsyncClient

from backend.core.beta_auth import CHALLENGE
from backend.core.config import Settings
from backend.main import create_app

USERNAME = "beta-user"
PASSWORD = "strong-beta-password"


def build_settings(*, enabled: bool, cors_origins: list[str] | None = None) -> Settings:
    return Settings(
        _env_file=None,
        beta_auth_enabled=enabled,
        beta_auth_username=USERNAME if enabled else None,
        beta_auth_password=PASSWORD if enabled else None,
        cors_origins=cors_origins or [],
    )


def basic_header(username: str, password: str) -> dict[str, str]:
    encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


async def request(path: str, settings: Settings, **kwargs):
    async with AsyncClient(
        transport=ASGITransport(app=create_app(settings)),
        base_url="http://test",
    ) as client:
        return await client.request(kwargs.pop("method", "GET"), path, **kwargs)


@pytest.mark.asyncio
async def test_disabled_auth_permits_protected_route() -> None:
    response = await request("/openapi.json", build_settings(enabled=False))

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_enabled_auth_requires_authorization_header() -> None:
    response = await request("/openapi.json", build_settings(enabled=True))

    assert_unauthorized(response)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("username", "password"),
    [
        ("wrong-user", PASSWORD),
        (USERNAME, "wrong-password"),
    ],
)
async def test_enabled_auth_rejects_invalid_credentials(
    username: str,
    password: str,
) -> None:
    response = await request(
        "/openapi.json",
        build_settings(enabled=True),
        headers=basic_header(username, password),
    )

    assert_unauthorized(response)


@pytest.mark.asyncio
async def test_enabled_auth_accepts_valid_credentials() -> None:
    response = await request(
        "/openapi.json",
        build_settings(enabled=True),
        headers=basic_header(USERNAME, PASSWORD),
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_remains_public() -> None:
    response = await request("/health", build_settings(enabled=True))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_options_remains_public() -> None:
    frontend_origin = "https://frontend.example"
    response = await request(
        "/api/conversations",
        build_settings(enabled=True, cors_origins=[frontend_origin]),
        method="OPTIONS",
        headers={
            "Origin": frontend_origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == frontend_origin


@pytest.mark.asyncio
async def test_admin_health_is_not_public() -> None:
    response = await request("/api/admin/health", build_settings(enabled=True))

    assert_unauthorized(response)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"])
async def test_fastapi_documentation_routes_are_protected(path: str) -> None:
    response = await request(path, build_settings(enabled=True))

    assert_unauthorized(response)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "authorization",
    [
        "Bearer token",
        "Basic !!!not-base64!!!",
        f"Basic {base64.b64encode(b'missing-separator').decode()}",
    ],
)
async def test_malformed_authorization_returns_generic_unauthorized(
    authorization: str,
) -> None:
    response = await request(
        "/openapi.json",
        build_settings(enabled=True),
        headers={"Authorization": authorization},
    )

    assert_unauthorized(response)


@pytest.mark.asyncio
async def test_unauthorized_response_does_not_expose_credentials() -> None:
    response = await request("/openapi.json", build_settings(enabled=True))
    response_content = f"{response.text} {response.headers}"

    assert USERNAME not in response_content
    assert PASSWORD not in response_content


def assert_unauthorized(response) -> None:
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == CHALLENGE
    assert response.json() == {"detail": "Unauthorized"}
