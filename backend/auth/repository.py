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
        role: UserRole = UserRole.STUDENT,
        first_name: str,
        last_name: str,
    ) -> UserAccount:
        user = UserAccount(
            clerk_id=clerk_id,
            role=role.value,
            first_name=first_name,
            last_name=last_name,
        )
        session.add(user)
        await session.flush()
        return user

    async def update_profile_projection(
        self,
        session: AsyncSession,
        *,
        user: UserAccount,
        first_name: str,
        last_name: str,
    ) -> bool:
        if user.first_name == first_name and user.last_name == last_name:
            return False

        user.first_name = first_name
        user.last_name = last_name
        await session.flush()
        return True
