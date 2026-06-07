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
    ) -> UserAccount:
        user = UserAccount(
            clerk_id=clerk_id,
            role=role.value,
        )
        session.add(user)
        await session.flush()
        return user
