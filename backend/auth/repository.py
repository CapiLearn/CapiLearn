from datetime import datetime

from sqlalchemy import case, or_, select
from sqlalchemy.dialects.postgresql import insert
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
        display_name: str,
        email: str | None = None,
        profile_synced_at: datetime,
    ) -> UserAccount:
        user = UserAccount(
            clerk_id=clerk_id,
            role=role.value,
            display_name=display_name,
            email=email,
            profile_synced_at=profile_synced_at,
        )
        session.add(user)
        await session.flush()
        return user

    async def update_profile_projection(
        self,
        session: AsyncSession,
        *,
        user: UserAccount,
        display_name: str,
        email: str | None,
        synced_at: datetime,
    ) -> bool:
        if user.display_name == display_name and user.email == email:
            return False

        user.display_name = display_name
        user.email = email
        user.profile_synced_at = synced_at
        await session.flush()
        return True

    async def upsert_from_clerk_profile(
        self,
        session: AsyncSession,
        *,
        clerk_id: str,
        display_name: str,
        email: str | None,
        clerk_profile_updated_at: datetime,
        synced_at: datetime,
        default_role: UserRole = UserRole.STUDENT,
    ) -> UserAccount:
        # Webhooks own profile projection only; app-owned role and soft-delete state stay intact.
        statement = insert(UserAccount).values(
            clerk_id=clerk_id,
            role=default_role.value,
            display_name=display_name,
            email=email,
            profile_synced_at=synced_at,
            clerk_profile_updated_at=clerk_profile_updated_at,
        )
        incoming_profile_updated_at = statement.excluded.clerk_profile_updated_at
        applies_profile_update = or_(
            UserAccount.clerk_profile_updated_at.is_(None),
            incoming_profile_updated_at >= UserAccount.clerk_profile_updated_at,
        )
        statement = (
            statement.on_conflict_do_update(
                index_elements=[UserAccount.clerk_id],
                set_={
                    "display_name": case(
                        (applies_profile_update, statement.excluded.display_name),
                        else_=UserAccount.display_name,
                    ),
                    "email": case(
                        (applies_profile_update, statement.excluded.email),
                        else_=UserAccount.email,
                    ),
                    "profile_synced_at": case(
                        (applies_profile_update, statement.excluded.profile_synced_at),
                        else_=UserAccount.profile_synced_at,
                    ),
                    "clerk_profile_updated_at": case(
                        (applies_profile_update, incoming_profile_updated_at),
                        else_=UserAccount.clerk_profile_updated_at,
                    ),
                    "updated_at": case(
                        (applies_profile_update, synced_at),
                        else_=UserAccount.updated_at,
                    ),
                },
            )
            .returning(UserAccount)
            .execution_options(populate_existing=True)
        )
        result = await session.execute(statement)
        return result.scalar_one()

    async def soft_delete_by_clerk_id(
        self,
        session: AsyncSession,
        *,
        clerk_id: str,
        deleted_at: datetime,
    ) -> bool:
        user = await self.get_by_clerk_id(session, clerk_id=clerk_id)
        if user is None or user.deleted_at is not None:
            return False

        user.deleted_at = deleted_at
        await session.flush()
        return True
