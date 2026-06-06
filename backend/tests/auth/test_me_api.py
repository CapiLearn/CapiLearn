from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from backend.auth.dependencies import get_auth_request_verifier, get_user_repository
from backend.auth.models import UserAccount
from backend.auth.repository import UserAccountRepository
from backend.auth.schemas import ClerkAuthClaims, UserRole
from backend.core.config import Settings, get_settings
from backend.core.database import get_db
from backend.core.exceptions import ApiError
from backend.main import app


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_me_requires_authorization_header() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/me")

    assert response.status_code == 401
    assert response.json() == {
        "code": "auth_required",
        "message": "Authentication is required.",
        "details": None,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("authorization", ["Basic token", "Bearer", "Bearer token extra"])
async def test_me_rejects_malformed_authorization(authorization: str) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/me", headers={"Authorization": authorization})

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_auth_token"


@pytest.mark.asyncio
async def test_me_rejects_invalid_clerk_state() -> None:
    app.dependency_overrides[get_db] = _fake_db_override(FakeSession())
    app.dependency_overrides[get_user_repository] = lambda: FakeUserRepository()
    app.dependency_overrides[get_auth_request_verifier] = lambda: FailingVerifier()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/me", headers={"Authorization": "Bearer invalid"})

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_auth_token"


@pytest.mark.asyncio
async def test_me_rejects_missing_clerk_config_in_default_clerk_mode() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        auth_mode="clerk",
        clerk_secret_key=None,
        clerk_jwt_key=None,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/me", headers={"Authorization": "Bearer invalid"})

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_auth_token"


@pytest.mark.asyncio
async def test_test_auth_mode_requires_bearer_auth() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(auth_mode="test")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/me")

    assert response.status_code == 401
    assert response.json()["code"] == "auth_required"


@pytest.mark.asyncio
async def test_test_auth_mode_creates_local_user_with_configured_claims() -> None:
    repository = FakeUserRepository()
    session = FakeSession()
    app.dependency_overrides[get_settings] = lambda: Settings(
        auth_mode="test",
        test_auth_clerk_id="user_test_mode",
        test_auth_email="dev@example.com",
        test_auth_display_name="Local Dev",
        test_auth_role="admin",
    )
    app.dependency_overrides[get_db] = _fake_db_override(session)
    app.dependency_overrides[get_user_repository] = lambda: repository

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/me?userId=00000000-0000-0000-0000-000000000000",
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "id": str(repository.user.id),
        "clerkId": "user_test_mode",
        "email": "dev@example.com",
        "displayName": "Local Dev",
        "role": "admin",
    }
    assert session.commits == 1
    assert repository.calls == [
        ("get_by_clerk_id", "user_test_mode"),
        ("create", "user_test_mode", "dev@example.com", "Local Dev", UserRole.ADMIN),
    ]


class FakeVerifier:
    def __init__(self, claims: ClerkAuthClaims) -> None:
        self._claims = claims

    async def verify(self, bearer_token: str):
        return self._claims


class FailingVerifier:
    async def verify(self, bearer_token: str):
        raise ApiError(
            code="invalid_auth_token",
            message="Invalid authentication token.",
            status_code=401,
        )


def _fake_db_override(session):
    async def override():
        yield session

    return override


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeUserRepository(UserAccountRepository):
    def __init__(self, user: UserAccount | None = None) -> None:
        self.user = user
        self.calls = []

    async def get_by_clerk_id(self, session, *, clerk_id: str) -> UserAccount | None:
        self.calls.append(("get_by_clerk_id", clerk_id))
        return self.user

    async def create(
        self,
        session,
        *,
        clerk_id: str,
        email: str | None = None,
        display_name: str | None = None,
        role: UserRole = UserRole.STUDENT,
    ) -> UserAccount:
        self.calls.append(("create", clerk_id, email, display_name, role))
        self.user = UserAccount(
            id=uuid4(),
            clerk_id=clerk_id,
            email=email,
            display_name=display_name,
            role=role.value,
        )
        return self.user

    def apply_profile_claims(
        self,
        user: UserAccount,
        *,
        email: str | None,
        display_name: str | None,
    ) -> bool:
        self.calls.append(("apply_profile_claims", email, display_name))
        return super().apply_profile_claims(
            user,
            email=email,
            display_name=display_name,
        )
