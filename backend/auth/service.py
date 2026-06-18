from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.models import UserAccount
from backend.auth.repository import UserAccountRepository
from backend.auth.schemas import (
    AuthPrincipal,
    ClerkAuthClaims,
    CurrentUser,
    UserRole,
    current_user_to_principal,
)
from backend.core.exceptions import ApiError


class AuthUserService:
    def __init__(self, repository: UserAccountRepository | None = None) -> None:
        self._repository = repository or UserAccountRepository()

    async def get_or_create_current_user(
        self,
        session: AsyncSession,
        claims: ClerkAuthClaims,
        *,
        initial_role: UserRole = UserRole.STUDENT,
    ) -> CurrentUser:
        user = await self._repository.get_by_clerk_id(session, clerk_id=claims.clerk_id)
        if user is None:
            user, _ = await self._create_user(
                session,
                clerk_id=claims.clerk_id,
                initial_role=initial_role,
            )

        _reject_disabled_user(user)

        return _current_user_from_model(user, claims=claims)

    async def get_existing_current_user(
        self,
        session: AsyncSession,
        claims: ClerkAuthClaims,
    ) -> CurrentUser | None:
        user = await self._repository.get_by_clerk_id(session, clerk_id=claims.clerk_id)
        if user is None:
            return None

        _reject_disabled_user(user)
        return _current_user_from_model(user, claims=claims)

    async def get_current_principal(
        self,
        session: AsyncSession,
        claims: ClerkAuthClaims,
    ) -> AuthPrincipal | None:
        current_user = await self.get_existing_current_user(session, claims)
        if current_user is None:
            return None
        return current_user_to_principal(current_user)

    async def _create_user(
        self,
        session: AsyncSession,
        *,
        clerk_id: str,
        initial_role: UserRole,
    ) -> tuple[UserAccount, bool]:
        try:
            user = await self._repository.create(
                session,
                clerk_id=clerk_id,
                role=initial_role,
            )
            await session.commit()
        except IntegrityError:
            await session.rollback()
            existing_user = await self._repository.get_by_clerk_id(
                session,
                clerk_id=clerk_id,
            )
            if existing_user is None:
                raise
            return existing_user, False
        return user, True


class AuthTestModeService:
    def __init__(
        self,
        repository: UserAccountRepository | None = None,
        *,
        role: UserRole,
    ) -> None:
        repository = repository or UserAccountRepository()
        self._auth_service = AuthUserService(repository=repository)
        self._role = role

    async def get_or_create_current_user(
        self,
        session: AsyncSession,
        claims: ClerkAuthClaims,
    ) -> CurrentUser:
        current_user = await self._auth_service.get_or_create_current_user(
            session,
            claims,
        )

        return CurrentUser(
            id=current_user.id,
            clerk_id=current_user.clerk_id,
            email=claims.email,
            display_name=claims.display_name,
            role=self._role,
        )

    async def get_current_principal(
        self,
        session: AsyncSession,
        claims: ClerkAuthClaims,
    ) -> AuthPrincipal:
        current_user = await self.get_or_create_current_user(
            session,
            claims,
        )
        return current_user_to_principal(current_user)


def _reject_disabled_user(user: UserAccount) -> None:
    if user.deleted_at is not None:
        raise ApiError(
            code="forbidden",
            message="This user account is disabled.",
            status_code=status.HTTP_403_FORBIDDEN,
        )


def _current_user_from_model(user: UserAccount, *, claims: ClerkAuthClaims) -> CurrentUser:
    try:
        role = UserRole(user.role)
    except ValueError as exc:
        raise ValueError(f"Invalid persisted user role: {user.role!r}") from exc
    return CurrentUser(
        id=user.id,
        clerk_id=user.clerk_id,
        email=claims.email,
        display_name=claims.display_name,
        role=role,
    )
