from datetime import datetime

from sqlalchemy import case, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.models import UserAccount, utc_now
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

    async def create_or_get_by_clerk_id(
        self,
        session: AsyncSession,
        *,
        clerk_id: str,
        role: UserRole = UserRole.STUDENT,
        first_name: str,
        last_name: str,
    ) -> tuple[UserAccount, bool]:
        statement = (
            insert(UserAccount)
            .values(
                clerk_id=clerk_id,
                role=role.value,
                first_name=first_name,
                last_name=last_name,
            )
            .on_conflict_do_nothing(index_elements=[UserAccount.clerk_id])
            .returning(UserAccount)
            .execution_options(populate_existing=True)
        )
        result = await session.execute(statement)
        user = result.scalar_one_or_none()
        if user is not None:
            return user, True

        existing_user = await self.get_by_clerk_id(session, clerk_id=clerk_id)
        if existing_user is None:
            raise RuntimeError(
                "Expected existing user_account after clerk_id conflict, but none was found."
            )
        return existing_user, False

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

    async def upsert_from_clerk_profile(
        self,
        session: AsyncSession,
        *,
        clerk_id: str,
        first_name: str,
        last_name: str,
        clerk_profile_updated_at: datetime,
        default_role: UserRole = UserRole.STUDENT,
    ) -> UserAccount:
        # Webhooks own profile projection only; app-owned role and soft-delete state stay intact.
        statement = insert(UserAccount).values(
            clerk_id=clerk_id,
            role=default_role.value,
            first_name=first_name,
            last_name=last_name,
            clerk_profile_updated_at=clerk_profile_updated_at,
        )
        updated_at = utc_now()
        incoming_profile_updated_at = statement.excluded.clerk_profile_updated_at
        applies_profile_update = or_(
            UserAccount.clerk_profile_updated_at.is_(None),
            incoming_profile_updated_at >= UserAccount.clerk_profile_updated_at,
        )
        statement = (
            statement.on_conflict_do_update(
                index_elements=[UserAccount.clerk_id],
                set_={
                    "first_name": case(
                        (applies_profile_update, statement.excluded.first_name),
                        else_=UserAccount.first_name,
                    ),
                    "last_name": case(
                        (applies_profile_update, statement.excluded.last_name),
                        else_=UserAccount.last_name,
                    ),
                    "clerk_profile_updated_at": case(
                        (applies_profile_update, incoming_profile_updated_at),
                        else_=UserAccount.clerk_profile_updated_at,
                    ),
                    "updated_at": case(
                        (applies_profile_update, updated_at),
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
