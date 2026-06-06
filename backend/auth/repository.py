from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.models import UserAccount
from backend.auth.schemas import UserRole


class UserAccountRepository:
    async def get_by_clerk_id(
        self,
        session: AsyncSession,
        *,
        clerk_id: str,
    ) -> UserAccount | None:
        statement = select(UserAccount).where(UserAccount.clerk_id == clerk_id)
        return await session.scalar(statement)

    async def create(
        self,
        session: AsyncSession,
        *,
        clerk_id: str,
        email: str | None = None,
        display_name: str | None = None,
        role: UserRole = UserRole.STUDENT,
    ) -> UserAccount:
        user = UserAccount(
            clerk_id=clerk_id,
            email=email,
            display_name=display_name,
            role=role.value,
        )
        session.add(user)
        await session.flush()
        return user

    def apply_profile_claims(
        self,
        user: UserAccount,
        *,
        email: str | None,
        display_name: str | None,
    ) -> bool:
        changed = False
        if email is not None and user.email != email:
            user.email = email
            changed = True
        if display_name is not None and user.display_name != display_name:
            user.display_name = display_name
            changed = True
        return changed
