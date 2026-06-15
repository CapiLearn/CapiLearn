from collections.abc import Callable
from typing import Annotated, Any, Protocol

from clerk_backend_api import Clerk
from clerk_backend_api.security.types import AuthenticateRequestOptions
from fastapi import Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.repository import UserAccountRepository
from backend.auth.schemas import (
    AuthPrincipal,
    ClerkAuthClaims,
    CurrentUser,
    UserRole,
)
from backend.auth.service import AuthTestModeService, AuthUserService
from backend.core.config import Settings, get_settings
from backend.core.database import DbSession
from backend.core.exceptions import ApiError

SettingsDep = Annotated[Settings, Depends(get_settings)]


class AuthRequestVerifier(Protocol):
    async def verify(self, bearer_token: str) -> ClerkAuthClaims: ...


class CurrentUserResolver(Protocol):
    async def get_or_create_current_user(
        self,
        session: AsyncSession,
        claims: ClerkAuthClaims,
    ) -> CurrentUser: ...

    async def get_existing_current_user(
        self,
        session: AsyncSession,
        claims: ClerkAuthClaims,
    ) -> CurrentUser | None: ...

    async def get_current_principal(
        self,
        session: AsyncSession,
        claims: ClerkAuthClaims,
    ) -> AuthPrincipal | None: ...


class ClerkRequestVerifier:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def verify(self, bearer_token: str) -> ClerkAuthClaims:
        if not self._settings.clerk_secret_key and not self._settings.clerk_jwt_key:
            raise ApiError(
                code="invalid_auth_token",
                message="Clerk authentication is not configured.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        sdk = Clerk(bearer_auth=self._settings.clerk_secret_key)
        request_state = await sdk.authenticate_request_async(
            _BearerRequest(bearer_token),
            AuthenticateRequestOptions(
                secret_key=self._settings.clerk_secret_key,
                jwt_key=self._settings.clerk_jwt_key,
                authorized_parties=self._settings.clerk_authorized_parties or None,
                accepts_token=["session_token"],
            ),
        )
        if not request_state.is_signed_in or request_state.payload is None:
            raise ApiError(
                code="invalid_auth_token",
                message="Invalid authentication token.",
                status_code=status.HTTP_401_UNAUTHORIZED,
                details=_auth_failure_details(request_state.reason),
            )
        return _claims_from_payload(request_state.payload)


class TestRequestVerifier:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def verify(self, _bearer_token: str) -> ClerkAuthClaims:
        payload: dict[str, Any] = {
            "sub": self._settings.test_auth_clerk_id,
            "role": self._settings.test_auth_role,
        }
        if self._settings.test_auth_email is not None:
            payload["email"] = self._settings.test_auth_email
        if self._settings.test_auth_first_name is not None:
            payload["first_name"] = self._settings.test_auth_first_name
        if self._settings.test_auth_last_name is not None:
            payload["last_name"] = self._settings.test_auth_last_name

        return _claims_from_payload(payload)


def get_auth_request_verifier(settings: SettingsDep) -> AuthRequestVerifier:
    if settings.auth_mode == "test":
        return TestRequestVerifier(settings)
    return ClerkRequestVerifier(settings)


AuthRequestVerifierDep = Annotated[
    AuthRequestVerifier,
    Depends(get_auth_request_verifier),
]


def get_clerk_request_verifier(settings: SettingsDep) -> AuthRequestVerifier:
    return get_auth_request_verifier(settings)


def get_user_repository() -> UserAccountRepository:
    return UserAccountRepository()


UserRepositoryDep = Annotated[UserAccountRepository, Depends(get_user_repository)]


def get_auth_user_service(
    settings: SettingsDep,
    repository: UserRepositoryDep,
) -> CurrentUserResolver:
    if settings.auth_mode == "test":
        return AuthTestModeService(
            repository=repository,
            role=UserRole(settings.test_auth_role),
        )
    return AuthUserService(repository=repository)


AuthUserServiceDep = Annotated[CurrentUserResolver, Depends(get_auth_user_service)]


async def require_clerk_auth(
    verifier: AuthRequestVerifierDep,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> ClerkAuthClaims:
    bearer_token = _extract_bearer_token(authorization)
    return await verifier.verify(bearer_token)


ClerkAuthClaimsDep = Annotated[ClerkAuthClaims, Depends(require_clerk_auth)]


async def get_current_user(
    session: DbSession,
    auth_claims: ClerkAuthClaimsDep,
    service: AuthUserServiceDep,
) -> CurrentUser:
    # Normal app requests read an already-provisioned local user.
    current_user = await service.get_existing_current_user(session, auth_claims)
    if current_user is None:
        raise ApiError(
            code="user_not_provisioned",
            message="User account has not been provisioned.",
            status_code=status.HTTP_409_CONFLICT,
        )
    return current_user


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


async def get_bootstrap_current_user(
    session: DbSession,
    auth_claims: ClerkAuthClaimsDep,
    service: AuthUserServiceDep,
) -> CurrentUser:
    # /api/me is the explicit first-use bootstrap and repair path.
    return await service.get_or_create_current_user(session, auth_claims)


BootstrapCurrentUserDep = Annotated[
    CurrentUser,
    Depends(get_bootstrap_current_user),
]


async def get_current_principal(
    session: DbSession,
    auth_claims: ClerkAuthClaimsDep,
    service: AuthUserServiceDep,
) -> AuthPrincipal | None:
    # Authorization checks load role state only; they never provision or repair profiles.
    return await service.get_current_principal(session, auth_claims)


AuthPrincipalDep = Annotated[
    AuthPrincipal | None,
    Depends(get_current_principal),
]


def require_role(*roles: UserRole) -> Callable[[AuthPrincipal], AuthPrincipal]:
    allowed_roles = set(roles)

    async def dependency(principal: AuthPrincipalDep) -> AuthPrincipal:
        if principal is None:
            _raise_role_error(allowed_roles)
        if principal.role not in allowed_roles:
            _raise_role_error(allowed_roles)
        return principal

    return dependency


require_admin = require_role(UserRole.ADMIN)
require_instructor_or_admin = require_role(UserRole.INSTRUCTOR, UserRole.ADMIN)


def _raise_role_error(allowed_roles: set[UserRole]) -> None:
    admin_only = allowed_roles == {UserRole.ADMIN}
    raise ApiError(
        code="admin_required" if admin_only else "forbidden",
        message=(
            "Admin access is required."
            if admin_only
            else "This user does not have access to this resource."
        ),
        status_code=status.HTTP_403_FORBIDDEN,
    )


class _BearerRequest:
    def __init__(self, bearer_token: str) -> None:
        self.headers = {"Authorization": f"Bearer {bearer_token}"}


def _extract_bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise ApiError(
            code="auth_required",
            message="Authentication is required.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    parts = authorization.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise ApiError(
            code="invalid_auth_token",
            message="Authorization must use the Bearer token scheme.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    return parts[1]


def _claims_from_payload(payload: dict[str, Any]) -> ClerkAuthClaims:
    clerk_id = payload.get("sub")
    if not isinstance(clerk_id, str) or not clerk_id:
        raise ApiError(
            code="invalid_auth_token",
            message="Authentication token is missing a Clerk user subject.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    return ClerkAuthClaims(
        clerk_id=clerk_id,
        claims=payload,
    )


def _auth_failure_details(reason: object) -> dict[str, str] | None:
    if reason is None:
        return None
    reason_value = getattr(reason, "value", None)
    if isinstance(reason_value, tuple) and reason_value:
        return {"reason": str(reason_value[0])}
    return {"reason": str(reason)}
