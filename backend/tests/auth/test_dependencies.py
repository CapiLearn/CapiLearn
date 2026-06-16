from inspect import signature
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import status

from backend.auth.dependencies import (
    ClerkRequestVerifier,
    _extract_bearer_token,
    get_auth_user_service,
    get_current_principal,
    get_current_user,
)
from backend.auth.repository import UserAccountRepository
from backend.auth.schemas import ClerkAuthClaims, CurrentUser, UserRole
from backend.auth.service import AuthTestModeService, AuthUserService
from backend.core.config import Settings
from backend.core.exceptions import ApiError


def test_clerk_user_id_claim_is_kept_as_string() -> None:
    claims = _claims_from_verifier_payload(
        {
            "sub": "user_not-a-uuid",
            "email": "person@example.com",
            "name": "Person Name",
        }
    )

    assert claims.clerk_id == "user_not-a-uuid"
    assert claims.email == "person@example.com"
    assert claims.display_name == "Person Name"


@pytest.mark.asyncio
async def test_clerk_verifier_rejects_missing_clerk_config() -> None:
    verifier = ClerkRequestVerifier(Settings(clerk_secret_key=None, clerk_jwt_key=None))

    try:
        await verifier.verify("test-token")
    except ApiError as exc:
        assert exc.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc.code == "invalid_auth_token"
    else:
        raise AssertionError("Expected missing Clerk config to be rejected.")


@pytest.mark.parametrize(
    ("authorization", "expected_token"),
    [
        ("Bearer test-token", "test-token"),
        ("bearer test-token", "test-token"),
        ("  Bearer   test-token  ", "test-token"),
    ],
)
def test_bearer_authorization_is_parsed_once(
    authorization: str,
    expected_token: str,
) -> None:
    assert _extract_bearer_token(authorization) == expected_token


@pytest.mark.parametrize(
    "authorization",
    ["Basic test-token", "Bearer", "Bearer token extra", ""],
)
def test_malformed_bearer_authorization_is_rejected(authorization: str) -> None:
    with pytest.raises(ApiError) as exc_info:
        _extract_bearer_token(authorization)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.code == "invalid_auth_token"


def test_missing_bearer_authorization_is_rejected() -> None:
    with pytest.raises(ApiError) as exc_info:
        _extract_bearer_token(None)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.code == "auth_required"


@pytest.mark.asyncio
async def test_clerk_verifier_passes_normalized_bearer_request(monkeypatch) -> None:
    captured = {}

    class FakeClerk:
        def __init__(self, *, bearer_auth: str | None) -> None:
            captured["bearer_auth"] = bearer_auth

        async def authenticate_request_async(self, request, options):
            captured["headers"] = request.headers
            captured["options"] = options
            return SimpleNamespace(
                is_signed_in=True,
                payload={"sub": "user_123"},
                reason=None,
            )

    monkeypatch.setattr("backend.auth.dependencies.Clerk", FakeClerk)

    verifier = ClerkRequestVerifier(
        Settings(
            clerk_secret_key="sk_test_123",
            clerk_jwt_key="jwt-key",
            clerk_authorized_parties=["https://app.example.com"],
        )
    )

    claims = await verifier.verify("raw-token")

    assert claims.clerk_id == "user_123"
    assert captured["bearer_auth"] == "sk_test_123"
    assert captured["headers"] == {"Authorization": "Bearer raw-token"}
    assert captured["options"].secret_key == "sk_test_123"
    assert captured["options"].jwt_key == "jwt-key"
    assert captured["options"].authorized_parties == ["https://app.example.com"]
    assert captured["options"].accepts_token == ["session_token"]


def test_current_user_dependency_uses_one_configured_auth_service() -> None:
    parameters = signature(get_current_user).parameters

    assert list(parameters) == ["request", "session", "auth_claims", "service"]
    assert "settings" not in parameters
    assert "test_service" not in parameters


def test_current_principal_dependency_uses_one_configured_auth_service() -> None:
    parameters = signature(get_current_principal).parameters

    assert list(parameters) == ["session", "auth_claims", "service"]
    assert "settings" not in parameters
    assert "test_service" not in parameters


def test_auth_user_service_dependency_selects_clerk_service() -> None:
    service = get_auth_user_service(
        Settings(auth_mode="clerk"),
        UserAccountRepository(),
    )

    assert isinstance(service, AuthUserService)


def test_auth_user_service_dependency_selects_test_mode_service() -> None:
    service = get_auth_user_service(
        Settings(auth_mode="test", test_auth_role="admin"),
        UserAccountRepository(),
    )

    assert isinstance(service, AuthTestModeService)


@pytest.mark.asyncio
async def test_current_user_dependency_stores_user_on_request_state() -> None:
    user = CurrentUser(
        id=uuid4(),
        clerk_id="user_state",
        role=UserRole.STUDENT,
    )
    request = SimpleNamespace(state=SimpleNamespace())
    claims = ClerkAuthClaims(clerk_id="user_state", claims={"sub": "user_state"})
    service = FakeCurrentUserResolver(user)
    session = object()

    resolved_user = await get_current_user(request, session, claims, service)

    assert resolved_user == user
    assert request.state.current_user == user
    assert service.calls == [(session, claims)]


def _claims_from_verifier_payload(payload: dict) -> ClerkAuthClaims:
    from backend.auth.dependencies import _claims_from_payload

    return _claims_from_payload(payload)


class FakeCurrentUserResolver:
    def __init__(self, user: CurrentUser) -> None:
        self._user = user
        self.calls = []

    async def get_or_create_current_user(
        self,
        session,
        claims: ClerkAuthClaims,
    ) -> CurrentUser:
        self.calls.append((session, claims))
        return self._user
