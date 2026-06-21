from inspect import signature
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import status

from backend.auth.dependencies import (
    ClerkRequestVerifier,
    _extract_bearer_token,
    get_auth_user_service,
    get_bootstrap_current_user,
    get_current_principal,
    get_current_user,
    require_admin,
    require_instructor_or_admin,
)
from backend.auth.dependencies import TestRequestVerifier as AuthTestRequestVerifier
from backend.auth.repository import UserAccountRepository
from backend.auth.schemas import AuthPrincipal, ClerkAuthClaims, CurrentUser, UserRole
from backend.auth.service import AuthTestModeService, AuthUserService
from backend.core.config import Settings
from backend.core.exceptions import ApiError


def test_claim_parser_preserves_subject_and_raw_payload() -> None:
    payload = {
        "sub": "user_not-a-uuid",
        "email": "person@example.com",
        "username": " person123 ",
        "first_name": "Person",
        "last_name": "Name",
        "name": "Ignored Name",
        "full_name": "Ignored Name",
        "display_name": "Ignored Name",
    }

    claims = _claims_from_verifier_payload(payload)

    assert claims.clerk_id == "user_not-a-uuid"
    assert claims.claims == payload


@pytest.mark.parametrize(
    "payload",
    [{}, {"sub": ""}, {"sub": None}, {"sub": 123}, {"sub": True}],
)
def test_claim_parser_rejects_missing_or_invalid_subject(payload: dict) -> None:
    with pytest.raises(ApiError) as exc_info:
        _claims_from_verifier_payload(payload)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.code == "invalid_auth_token"


@pytest.mark.asyncio
async def test_test_verifier_uses_clerk_profile_claim_parser() -> None:
    claims = await AuthTestRequestVerifier(
        Settings(
            auth_mode="test",
            test_auth_clerk_id="user_test",
            test_auth_first_name="Local",
            test_auth_last_name="Dev",
        )
    ).verify("test-token")

    assert claims.clerk_id == "user_test"
    assert claims.claims == {
        "sub": "user_test",
        "role": "student",
        "first_name": "Local",
        "last_name": "Dev",
    }


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
                payload={"sub": "user_123", "first_name": "Test", "last_name": "User"},
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


@pytest.mark.asyncio
async def test_clerk_verifier_accepts_authenticated_subject_without_profile_claims(
    monkeypatch,
) -> None:
    class FakeClerk:
        def __init__(self, *, bearer_auth: str | None) -> None:
            pass

        async def authenticate_request_async(self, request, options):
            return SimpleNamespace(
                is_signed_in=True,
                payload={"sub": "user_123"},
                reason=None,
            )

    monkeypatch.setattr("backend.auth.dependencies.Clerk", FakeClerk)

    verifier = ClerkRequestVerifier(Settings(clerk_secret_key="sk_test_123"))

    claims = await verifier.verify("raw-token")

    assert claims.clerk_id == "user_123"
    assert claims.claims == {"sub": "user_123"}


def test_current_user_dependency_uses_one_configured_auth_service() -> None:
    parameters = signature(get_current_user).parameters

    assert list(parameters) == ["session", "auth_claims", "service"]
    assert "settings" not in parameters
    assert "test_service" not in parameters


def test_bootstrap_current_user_dependency_uses_one_configured_auth_service() -> None:
    parameters = signature(get_bootstrap_current_user).parameters

    assert list(parameters) == ["session", "auth_claims", "service"]
    assert "settings" not in parameters
    assert "test_service" not in parameters


def test_current_principal_dependency_uses_one_configured_auth_service() -> None:
    parameters = signature(get_current_principal).parameters

    assert list(parameters) == ["session", "auth_claims", "service"]
    assert "settings" not in parameters
    assert "test_service" not in parameters


@pytest.mark.asyncio
async def test_current_user_dependency_reads_existing_user_without_bootstrap() -> None:
    current_user = CurrentUser(
        id=uuid4(),
        clerk_id="user_existing",
        display_name="Stored User",
        role=UserRole.STUDENT,
    )
    service = FakeCurrentUserService(existing_user=current_user)

    resolved = await get_current_user(
        object(),
        ClerkAuthClaims(clerk_id="user_existing", claims={"sub": "user_existing"}),
        service,
    )

    assert resolved is current_user
    assert service.calls == [("get_existing_current_user", "user_existing")]


@pytest.mark.asyncio
async def test_current_user_dependency_rejects_missing_local_user_without_bootstrap() -> None:
    service = FakeCurrentUserService(existing_user=None)

    with pytest.raises(ApiError) as exc_info:
        await get_current_user(
            object(),
            ClerkAuthClaims(clerk_id="user_missing", claims={"sub": "user_missing"}),
            service,
        )

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert exc_info.value.code == "user_not_provisioned"
    assert service.calls == [("get_existing_current_user", "user_missing")]


@pytest.mark.asyncio
async def test_bootstrap_current_user_dependency_may_create_or_repair_user() -> None:
    current_user = CurrentUser(
        id=uuid4(),
        clerk_id="user_bootstrap",
        display_name="Bootstrap User",
        role=UserRole.STUDENT,
    )
    service = FakeCurrentUserService(existing_user=None, bootstrap_user=current_user)

    resolved = await get_bootstrap_current_user(
        object(),
        ClerkAuthClaims(clerk_id="user_bootstrap", claims={"sub": "user_bootstrap"}),
        service,
    )

    assert resolved is current_user
    assert service.calls == [("get_or_create_current_user", "user_bootstrap")]


@pytest.mark.asyncio
async def test_current_principal_dependency_reads_principal_without_bootstrap() -> None:
    principal = AuthPrincipal(clerk_id="user_admin", role=UserRole.ADMIN)
    service = FakeCurrentUserService(existing_user=None, principal=principal)

    resolved = await get_current_principal(
        object(),
        ClerkAuthClaims(clerk_id="user_admin", claims={"sub": "user_admin"}),
        service,
    )

    assert resolved is principal
    assert service.calls == [("get_current_principal", "user_admin")]


@pytest.mark.asyncio
async def test_current_principal_dependency_returns_none_without_bootstrap() -> None:
    service = FakeCurrentUserService(existing_user=None, principal=None)

    resolved = await get_current_principal(
        object(),
        ClerkAuthClaims(clerk_id="user_missing", claims={"sub": "user_missing"}),
        service,
    )

    assert resolved is None
    assert service.calls == [("get_current_principal", "user_missing")]


@pytest.mark.asyncio
async def test_admin_role_dependency_accepts_admin_principal() -> None:
    principal = AuthPrincipal(clerk_id="user_admin", role=UserRole.ADMIN)

    resolved = await require_admin(principal)

    assert resolved is principal
    assert list(signature(require_admin).parameters) == ["principal"]


@pytest.mark.asyncio
async def test_role_dependency_accepts_instructor_or_admin_principal() -> None:
    principal = AuthPrincipal(clerk_id="user_instructor", role=UserRole.INSTRUCTOR)

    resolved = await require_instructor_or_admin(principal)

    assert resolved is principal
    assert list(signature(require_instructor_or_admin).parameters) == ["principal"]


@pytest.mark.asyncio
async def test_admin_role_dependency_rejects_missing_principal_without_bootstrap() -> None:
    with pytest.raises(ApiError) as exc_info:
        await require_admin(None)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.code == "admin_required"


@pytest.mark.asyncio
async def test_instructor_or_admin_dependency_rejects_missing_principal_without_bootstrap() -> None:
    with pytest.raises(ApiError) as exc_info:
        await require_instructor_or_admin(None)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.code == "forbidden"


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


def _claims_from_verifier_payload(payload: dict) -> ClerkAuthClaims:
    from backend.auth.dependencies import _claims_from_payload

    return _claims_from_payload(payload)


class FakeCurrentUserService:
    def __init__(
        self,
        *,
        existing_user: CurrentUser | None,
        bootstrap_user: CurrentUser | None = None,
        principal: AuthPrincipal | None = None,
    ) -> None:
        self._existing_user = existing_user
        self._bootstrap_user = bootstrap_user
        self._principal = principal
        self.calls = []

    async def get_existing_current_user(self, session, claims):
        self.calls.append(("get_existing_current_user", claims.clerk_id))
        return self._existing_user

    async def get_or_create_current_user(self, session, claims):
        self.calls.append(("get_or_create_current_user", claims.clerk_id))
        return self._bootstrap_user

    async def get_current_principal(self, session, claims):
        self.calls.append(("get_current_principal", claims.clerk_id))
        return self._principal
