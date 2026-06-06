from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.models import UserAccount
from backend.auth.repository import UserAccountRepository
from backend.auth.schemas import ClerkAuthClaims, CurrentUser, UserRole
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
        role_override: UserRole | None = None,
    ) -> CurrentUser:
        user = await self._repository.get_by_clerk_id(session, clerk_id=claims.clerk_id)
        created = False
        if user is None:
            user, created = await self._create_user(
                session,
                claims,
                initial_role=initial_role,
            )

        if user.deleted_at is not None:
            raise ApiError(
                code="forbidden",
                message="This user account is disabled.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        if not created:
            profile_changed = self._repository.apply_profile_claims(
                user,
                email=claims.email,
                display_name=claims.display_name,
            )
            role_changed = (
                self._repository.apply_role(user, role_override)
                if role_override is not None
                else False
            )
            if profile_changed or role_changed:
                await session.commit()
        return _current_user_from_model(user)

    async def _create_user(
        self,
        session: AsyncSession,
        claims: ClerkAuthClaims,
        *,
        initial_role: UserRole,
    ) -> tuple[UserAccount, bool]:
        try:
            user = await self._repository.create(
                session,
                clerk_id=claims.clerk_id,
                email=claims.email,
                display_name=claims.display_name,
                role=initial_role,
            )
            await session.commit()
        except IntegrityError:
            await session.rollback()
            existing_user = await self._repository.get_by_clerk_id(
                session,
                clerk_id=claims.clerk_id,
            )
            if existing_user is None:
                raise
            return existing_user, False
        return user, True


def _current_user_from_model(user: UserAccount) -> CurrentUser:
    try:
        role = UserRole(user.role)
    except ValueError as exc:
        raise ApiError(
            code="forbidden",
            message="This user account has an invalid role.",
            status_code=status.HTTP_403_FORBIDDEN,
        ) from exc
    return CurrentUser(
        id=user.id,
        clerk_id=user.clerk_id,
        email=user.email,
        display_name=user.display_name,
        role=role,
    )
