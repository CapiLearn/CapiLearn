import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from backend.auth.dependencies import get_sign_in_token_client
from backend.core.config import Settings, get_settings
from backend.core.exceptions import ApiError
from backend.main import app


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_demo_admin_sign_in_token_returns_404_when_disabled() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        demo_admin_login_enabled=False,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/auth/demo-admin/sign-in-token")

    assert response.status_code == 404
    assert response.json() == {
        "code": "not_found",
        "message": "Not found.",
        "details": None,
    }


@pytest.mark.asyncio
async def test_demo_admin_sign_in_token_rejects_missing_demo_admin_user_id() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        demo_admin_login_enabled=True,
        demo_admin_clerk_user_id=None,
        clerk_secret_key="sk_test_123",
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/auth/demo-admin/sign-in-token")

    assert response.status_code == 500
    assert response.json() == {
        "code": "demo_admin_login_not_configured",
        "message": "Demo admin login is not configured.",
        "details": None,
    }


@pytest.mark.asyncio
async def test_demo_admin_sign_in_token_rejects_missing_clerk_secret_key() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        demo_admin_login_enabled=True,
        demo_admin_clerk_user_id="user_demo_admin",
        clerk_secret_key=None,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/auth/demo-admin/sign-in-token")

    assert response.status_code == 500
    assert response.json() == {
        "code": "clerk_secret_key_not_configured",
        "message": "Clerk sign-in token creation is not configured.",
        "details": None,
    }


@pytest.mark.asyncio
async def test_demo_admin_sign_in_token_returns_token_from_configured_client() -> None:
    sign_in_token_client = FakeSignInTokenClient(token="ticket_demo_admin")
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        demo_admin_login_enabled=True,
        demo_admin_clerk_user_id=" user_demo_admin ",
        demo_admin_sign_in_token_ttl_seconds=120,
        clerk_secret_key="sk_test_123",
    )
    app.dependency_overrides[get_sign_in_token_client] = lambda: sign_in_token_client

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/auth/demo-admin/sign-in-token")

    assert response.status_code == 200
    assert response.json() == {"token": "ticket_demo_admin"}
    assert sign_in_token_client.calls == [
        ("create_sign_in_token", "user_demo_admin", 120),
    ]


@pytest.mark.asyncio
async def test_demo_admin_sign_in_token_maps_client_failure() -> None:
    sign_in_token_client = FakeSignInTokenClient(
        error=ApiError(
            code="clerk_sign_in_token_failed",
            message="Unable to create demo admin sign-in token.",
            status_code=502,
            details={"errors": [{"code": "not_found", "message": "User not found."}]},
        )
    )
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        demo_admin_login_enabled=True,
        demo_admin_clerk_user_id="user_demo_admin",
        clerk_secret_key="sk_test_123",
    )
    app.dependency_overrides[get_sign_in_token_client] = lambda: sign_in_token_client

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/auth/demo-admin/sign-in-token")

    assert response.status_code == 502
    assert response.json() == {
        "code": "clerk_sign_in_token_failed",
        "message": "Unable to create demo admin sign-in token.",
        "details": {"errors": [{"code": "not_found", "message": "User not found."}]},
    }


def test_demo_admin_sign_in_token_ttl_is_clamped_to_five_minutes() -> None:
    settings = Settings(
        _env_file=None,
        demo_admin_sign_in_token_ttl_seconds=999,
    )

    assert settings.demo_admin_sign_in_token_ttl_seconds == 300


def test_demo_admin_sign_in_token_ttl_rejects_non_positive_values() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            demo_admin_sign_in_token_ttl_seconds=0,
        )


class FakeSignInTokenClient:
    def __init__(
        self,
        *,
        token: str = "ticket_test",
        error: ApiError | None = None,
    ) -> None:
        self.token = token
        self.error = error
        self.calls: list[tuple[str, str, int]] = []

    async def create_sign_in_token(
        self,
        *,
        user_id: str,
        expires_in_seconds: int,
    ) -> str:
        self.calls.append(("create_sign_in_token", user_id, expires_in_seconds))
        if self.error is not None:
            raise self.error
        return self.token
