import pytest
from httpx import ASGITransport, AsyncClient

from backend.auth.dependencies import get_auth_request_verifier, get_user_repository
from backend.core.config import Settings, get_settings
from backend.core.database import get_db
from backend.core.exceptions import ApiError
from backend.main import app
from backend.tests.fakes import FakeUserRepository


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
async def test_me_bootstraps_current_user_response() -> None:
    repository = FakeUserRepository()
    session = FakeSession()
    app.dependency_overrides[get_settings] = lambda: Settings(
        auth_mode="test",
        test_auth_clerk_id="user_test_mode",
        test_auth_first_name="Local",
        test_auth_last_name="Dev",
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
        "displayName": "Local Dev",
        "role": "admin",
    }


@pytest.mark.asyncio
async def test_me_rejects_incomplete_test_auth_profile_claims() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        auth_mode="test",
        test_auth_clerk_id="user_test_mode",
        test_auth_first_name="Local",
        test_auth_last_name=None,
    )
    app.dependency_overrides[get_db] = _fake_db_override(FakeSession())
    app.dependency_overrides[get_user_repository] = lambda: FakeUserRepository()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/me",
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 409
    assert response.json() == {
        "code": "profile_incomplete",
        "message": "Complete your profile before using the app.",
        "details": None,
    }


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
        self.flushes = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def flush(self) -> None:
        self.flushes += 1
