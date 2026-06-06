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
    ) -> CurrentUser:
        user = await self._repository.get_by_clerk_id(session, clerk_id=claims.clerk_id)
        if user is None:
            user = await self._create_user(
                session,
                claims,
                initial_role=initial_role,
            )
        elif user.deleted_at is None and self._repository.apply_profile_claims(
            user,
            email=claims.email,
            display_name=claims.display_name,
        ):
            await session.commit()

        if user.deleted_at is not None:
            raise ApiError(
                code="forbidden",
                message="This user account is disabled.",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        return _current_user_from_model(user)

    async def _create_user(
        self,
        session: AsyncSession,
        claims: ClerkAuthClaims,
        *,
        initial_role: UserRole,
    ) -> UserAccount:
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
            return existing_user
        return user


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
