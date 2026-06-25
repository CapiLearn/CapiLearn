from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.models import UserAccount
from backend.auth.profile_projection import profile_from_clerk_payload
from backend.auth.repository import UserAccountRepository
from backend.auth.schemas import (
    AuthPrincipal,
    ClerkAuthClaims,
    CurrentUser,
    UserRole,
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
            user, created = await self._create_user(
                session,
                claims=claims,
                initial_role=initial_role,
            )
            if not created:
                await self._repair_unwebhooked_profile_from_claims(
                    session,
                    user=user,
                    claims=claims,
                )
            else:
                _reject_disabled_user(user)
            return _current_user_from_model(user)

        await self._repair_unwebhooked_profile_from_claims(session, user=user, claims=claims)

        return _current_user_from_model(user)

    async def get_existing_current_user(
        self,
        session: AsyncSession,
        claims: ClerkAuthClaims,
    ) -> CurrentUser | None:
        user = await self._repository.get_by_clerk_id(session, clerk_id=claims.clerk_id)
        if user is None:
            return None

        _reject_disabled_user(user)
        return _current_user_from_model(user)

    async def get_current_principal(
        self,
        session: AsyncSession,
        claims: ClerkAuthClaims,
    ) -> AuthPrincipal | None:
        user = await self._repository.get_by_clerk_id(session, clerk_id=claims.clerk_id)
        if user is None:
            return None
        _reject_disabled_user(user)
        return _principal_from_model(user)

    async def _create_user(
        self,
        session: AsyncSession,
        *,
        claims: ClerkAuthClaims,
        initial_role: UserRole,
    ) -> tuple[UserAccount, bool]:
        profile = profile_from_clerk_payload(claims.claims)
        try:
            user, created = await self._repository.create_or_get_by_clerk_id(
                session,
                clerk_id=claims.clerk_id,
                role=initial_role,
                first_name=profile.first_name,
                last_name=profile.last_name,
            )
            if created:
                await session.commit()
        except IntegrityError:
            await session.rollback()
            raise
        return user, created

    async def _repair_unwebhooked_profile_from_claims(
        self,
        session: AsyncSession,
        *,
        user: UserAccount,
        claims: ClerkAuthClaims,
    ) -> None:
        # Only /api/me bootstrap uses session claims as a narrow fallback before webhook sync.
        _reject_disabled_user(user)
        if user.clerk_profile_updated_at is not None:
            return

        profile = profile_from_clerk_payload(claims.claims)
        profile_synced = await self._repository.update_profile_projection(
            session,
            user=user,
            first_name=profile.first_name,
            last_name=profile.last_name,
        )
        if profile_synced:
            await session.commit()


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
            display_name=current_user.display_name,
            role=self._role,
        )

    async def get_existing_current_user(
        self,
        session: AsyncSession,
        claims: ClerkAuthClaims,
    ) -> CurrentUser | None:
        current_user = await self._auth_service.get_existing_current_user(
            session,
            claims,
        )
        if current_user is None:
            return None

        return CurrentUser(
            id=current_user.id,
            clerk_id=current_user.clerk_id,
            display_name=current_user.display_name,
            role=self._role,
        )

    async def get_current_principal(
        self,
        session: AsyncSession,
        claims: ClerkAuthClaims,
    ) -> AuthPrincipal | None:
        principal = await self._auth_service.get_current_principal(
            session,
            claims,
        )
        if principal is None:
            return None

        return AuthPrincipal(
            clerk_id=principal.clerk_id,
            role=self._role,
        )


def _reject_disabled_user(user: UserAccount) -> None:
    if user.deleted_at is not None:
        raise ApiError(
            code="forbidden",
            message="This user account is disabled.",
            status_code=status.HTTP_403_FORBIDDEN,
        )


def _current_user_from_model(user: UserAccount) -> CurrentUser:
    role = _role_from_model(user)
    return CurrentUser(
        id=user.id,
        clerk_id=user.clerk_id,
        display_name=f"{user.first_name} {user.last_name}",
        role=role,
    )


def _principal_from_model(user: UserAccount) -> AuthPrincipal:
    role = _role_from_model(user)
    return AuthPrincipal(
        clerk_id=user.clerk_id,
        role=role,
    )


def _role_from_model(user: UserAccount) -> UserRole:
    try:
        return UserRole(user.role)
    except ValueError as exc:
        raise ApiError(
            code="forbidden",
            message="This user account has an invalid role.",
            status_code=status.HTTP_403_FORBIDDEN,
        ) from exc
