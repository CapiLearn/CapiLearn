import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from backend.auth import clerk_sign_in_tokens
from backend.auth.clerk_sign_in_tokens import ClerkSignInTokenClient
from backend.auth.dependencies import get_sign_in_token_client
from backend.core.config import Settings, get_settings
from backend.core.exceptions import ApiError
from backend.core.rate_limiting import DEMO_ADMIN_LOGIN_RATE_LIMIT, limiter
from backend.main import app


@pytest.fixture(autouse=True)
def clear_overrides():
    limiter.reset()
    yield
    app.dependency_overrides.clear()
    limiter.reset()


@pytest.mark.asyncio
async def test_demo_admin_sign_in_token_returns_404_with_default_config() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)

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
async def test_demo_admin_sign_in_token_rejects_missing_demo_admin_email() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        demo_admin_login_enabled=True,
        demo_admin_email=" ",
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
        demo_admin_email="admin+demo@example.com",
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
        demo_admin_email=" admin+demo@example.com ",
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
        ("create_sign_in_token_for_email", "admin+demo@example.com", 120),
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
        demo_admin_email="admin+demo@example.com",
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


@pytest.mark.asyncio
async def test_demo_admin_sign_in_token_is_rate_limited_by_ip() -> None:
    sign_in_token_client = FakeSignInTokenClient(token="ticket_demo_admin")
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        demo_admin_login_enabled=True,
        demo_admin_email="admin+demo@example.com",
        clerk_secret_key="sk_test_123",
    )
    app.dependency_overrides[get_sign_in_token_client] = lambda: sign_in_token_client

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        responses = [
            await client.post(
                "/api/auth/demo-admin/sign-in-token",
                headers={"X-Forwarded-For": "203.0.113.10"},
            )
            for _ in range(11)
        ]

    assert [response.status_code for response in responses[:10]] == [200] * 10
    assert responses[10].status_code == 429
    assert responses[10].json() == {
        "code": "rate_limited",
        "message": "Too many admin login attempts. Please wait and try again.",
        "details": {"limit": DEMO_ADMIN_LOGIN_RATE_LIMIT},
    }
    assert len(sign_in_token_client.calls) == 10


def test_demo_admin_sign_in_token_ttl_is_clamped_to_five_minutes() -> None:
    settings = Settings(
        _env_file=None,
        demo_admin_sign_in_token_ttl_seconds=999,
    )

    assert settings.demo_admin_sign_in_token_ttl_seconds == 300


def test_demo_admin_login_defaults_to_disabled_without_email() -> None:
    settings = Settings(_env_file=None)

    assert settings.demo_admin_login_enabled is False
    assert settings.demo_admin_email == ""


@pytest.mark.asyncio
async def test_clerk_sign_in_token_client_resolves_user_by_email(monkeypatch) -> None:
    clerk = FakeClerk(
        users=[FakeClerkUser(id="user_demo_admin")],
        token="ticket_demo_admin",
    )
    monkeypatch.setattr(clerk_sign_in_tokens, "Clerk", clerk)
    client = ClerkSignInTokenClient(Settings(_env_file=None, clerk_secret_key="sk_test_123"))

    token = await client.create_sign_in_token_for_email(
        email_address=" admin+demo@example.com ",
        expires_in_seconds=120,
    )

    assert token == "ticket_demo_admin"
    assert clerk.bearer_auth == "sk_test_123"
    assert clerk.users.requests == [
        {"email_address": ["admin+demo@example.com"], "limit": 2},
    ]
    assert clerk.sign_in_tokens.requests == [
        {"user_id": "user_demo_admin", "expires_in_seconds": 120},
    ]


@pytest.mark.asyncio
async def test_clerk_sign_in_token_client_rejects_missing_email_user(monkeypatch) -> None:
    clerk = FakeClerk(users=[], token="ticket_demo_admin")
    monkeypatch.setattr(clerk_sign_in_tokens, "Clerk", clerk)
    client = ClerkSignInTokenClient(Settings(_env_file=None, clerk_secret_key="sk_test_123"))

    with pytest.raises(ApiError) as exc_info:
        await client.create_sign_in_token_for_email(
            email_address="admin+missing@example.com",
            expires_in_seconds=120,
        )

    assert exc_info.value.code == "demo_admin_login_not_configured"
    assert clerk.sign_in_tokens.requests == []


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

    async def create_sign_in_token_for_email(
        self,
        *,
        email_address: str,
        expires_in_seconds: int,
    ) -> str:
        self.calls.append(("create_sign_in_token_for_email", email_address, expires_in_seconds))
        if self.error is not None:
            raise self.error
        return self.token


class FakeClerk:
    def __init__(self, *, users, token: str) -> None:
        self.bearer_auth = None
        self.users = FakeClerkUsers(users)
        self.sign_in_tokens = FakeClerkSignInTokens(token)

    def __call__(self, *, bearer_auth: str) -> "FakeClerk":
        self.bearer_auth = bearer_auth
        return self


class FakeClerkUsers:
    def __init__(self, users) -> None:
        self._users = users
        self.requests = []

    async def list_async(self, *, request):
        self.requests.append(request)
        return self._users


class FakeClerkSignInTokens:
    def __init__(self, token: str) -> None:
        self._token = token
        self.requests = []

    async def create_async(self, *, request):
        self.requests.append(request)
        return FakeClerkSignInToken(token=self._token)


class FakeClerkUser:
    def __init__(self, *, id: str) -> None:
        self.id = id


class FakeClerkSignInToken:
    def __init__(self, *, token: str) -> None:
        self.token = token
