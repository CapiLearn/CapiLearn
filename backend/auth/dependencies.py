from collections.abc import Callable
from typing import Annotated, Any, Protocol
from uuid import UUID

from clerk_backend_api import Clerk
from clerk_backend_api.security.types import AuthenticateRequestOptions
from fastapi import Depends, Header, status

from backend.auth.repository import UserAccountRepository
from backend.auth.schemas import ClerkAuthClaims, CurrentUser, UserRole
from backend.auth.service import AuthUserService
from backend.core.config import Settings, get_settings
from backend.core.database import DbSession
from backend.core.exceptions import ApiError

SettingsDep = Annotated[Settings, Depends(get_settings)]


class AuthRequestVerifier(Protocol):
    async def verify(self, bearer_token: str) -> ClerkAuthClaims: ...


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
        return ClerkAuthClaims(
            clerk_id=self._settings.test_auth_clerk_id,
            email=self._settings.test_auth_email,
            display_name=self._settings.test_auth_display_name,
            claims={
                "sub": self._settings.test_auth_clerk_id,
                "email": self._settings.test_auth_email,
                "name": self._settings.test_auth_display_name,
                "role": self._settings.test_auth_role,
            },
        )


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


def get_auth_user_service(repository: UserRepositoryDep) -> AuthUserService:
    return AuthUserService(repository=repository)


AuthUserServiceDep = Annotated[AuthUserService, Depends(get_auth_user_service)]


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
    repository: UserRepositoryDep,
    settings: SettingsDep,
) -> CurrentUser:
    if settings.auth_mode == "test":
        return await _get_or_create_test_current_user(
            session,
            auth_claims,
            service=service,
            repository=repository,
            settings=settings,
        )

    return await service.get_or_create_current_user(
        session,
        auth_claims,
        initial_role=UserRole.STUDENT,
    )


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


async def get_existing_current_user(
    session: DbSession,
    auth_claims: ClerkAuthClaimsDep,
    service: AuthUserServiceDep,
    settings: SettingsDep,
) -> CurrentUser | None:
    if settings.auth_mode == "test":
        return await _get_existing_test_current_user(
            session,
            auth_claims,
            service=service,
            settings=settings,
        )

    try:
        return await service.get_existing_current_user(session, auth_claims)
    except ApiError as exc:
        if _is_disabled_user_error(exc):
            return None
        raise


ExistingCurrentUserDep = Annotated[
    CurrentUser | None,
    Depends(get_existing_current_user),
]


def require_role(*roles: UserRole) -> Callable[[CurrentUser], CurrentUser]:
    allowed_roles = set(roles)

    async def dependency(current_user: ExistingCurrentUserDep) -> CurrentUser:
        if current_user is None:
            _raise_role_error(allowed_roles)
        if current_user.role not in allowed_roles:
            _raise_role_error(allowed_roles)
        return current_user

    return dependency


require_admin = require_role(UserRole.ADMIN)
require_instructor_or_admin = require_role(UserRole.INSTRUCTOR, UserRole.ADMIN)


async def _get_or_create_test_current_user(
    session: DbSession,
    claims: ClerkAuthClaims,
    *,
    service: AuthUserService,
    repository: UserAccountRepository,
    settings: Settings,
) -> CurrentUser:
    test_role = UserRole(settings.test_auth_role)
    current_user = await service.get_or_create_current_user(
        session,
        claims,
        initial_role=test_role,
    )
    if current_user.role == test_role:
        return current_user

    user = await repository.get_by_clerk_id(session, clerk_id=claims.clerk_id)
    if user is not None and repository.apply_role(user, test_role):
        await session.commit()

    return CurrentUser(
        id=current_user.id,
        clerk_id=current_user.clerk_id,
        email=claims.email,
        display_name=claims.display_name,
        role=test_role,
    )


async def _get_existing_test_current_user(
    session: DbSession,
    claims: ClerkAuthClaims,
    *,
    service: AuthUserService,
    settings: Settings,
) -> CurrentUser | None:
    try:
        current_user = await service.get_existing_current_user(session, claims)
    except ApiError as exc:
        if _is_disabled_user_error(exc):
            return None
        raise

    if current_user is None:
        return _synthetic_test_current_user(settings)
    return _current_user_with_role(current_user, UserRole(settings.test_auth_role))


def _synthetic_test_current_user(settings: Settings) -> CurrentUser:
    return CurrentUser(
        id=UUID(int=0),
        clerk_id=settings.test_auth_clerk_id,
        email=settings.test_auth_email,
        display_name=settings.test_auth_display_name,
        role=UserRole(settings.test_auth_role),
    )


def _current_user_with_role(current_user: CurrentUser, role: UserRole) -> CurrentUser:
    return CurrentUser(
        id=current_user.id,
        clerk_id=current_user.clerk_id,
        email=current_user.email,
        display_name=current_user.display_name,
        role=role,
    )


def _is_disabled_user_error(exc: ApiError) -> bool:
    return (
        exc.code == "forbidden"
        and exc.message == "This user account is disabled."
        and exc.status_code == status.HTTP_403_FORBIDDEN
    )


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
        email=_email_from_payload(payload),
        display_name=_display_name_from_payload(payload),
        claims=payload,
    )


def _email_from_payload(payload: dict[str, Any]) -> str | None:
    email = payload.get("email") or payload.get("email_address")
    return email if isinstance(email, str) and email else None


def _display_name_from_payload(payload: dict[str, Any]) -> str | None:
    for key in ("name", "full_name", "display_name", "username"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    first_name = payload.get("first_name")
    last_name = payload.get("last_name")
    name_parts = [
        value.strip()
        for value in (first_name, last_name)
        if isinstance(value, str) and value.strip()
    ]
    return " ".join(name_parts) or None


def _auth_failure_details(reason: object) -> dict[str, str] | None:
    if reason is None:
        return None
    reason_value = getattr(reason, "value", None)
    if isinstance(reason_value, tuple) and reason_value:
        return {"reason": str(reason_value[0])}
    return {"reason": str(reason)}
