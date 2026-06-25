"""Database access for student daily activity."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.activity.models import StudentDailyActivity


class StudentDailyActivityRepository:
    """Persists and queries per-student daily login activity rows."""

    async def record_login(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        activity_date: date,
        seen_at: datetime,
    ) -> StudentDailyActivity:
        """Create or update the user's activity row for one activity date."""
        # The unique user/date row is updated atomically so concurrent logins cannot split counts.
        statement = (
            insert(StudentDailyActivity)
            .values(
                user_id=user_id,
                activity_date=activity_date,
                first_seen_at=seen_at,
                last_seen_at=seen_at,
                login_count=1,
            )
            .on_conflict_do_update(
                index_elements=[
                    StudentDailyActivity.user_id,
                    StudentDailyActivity.activity_date,
                ],
                set_={
                    "last_seen_at": seen_at,
                    "login_count": StudentDailyActivity.login_count + 1,
                },
            )
            .returning(StudentDailyActivity)
            .execution_options(populate_existing=True)
        )
        result = await session.execute(statement)
        return result.scalar_one()

    async def list_dates_through(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        through_date: date,
    ) -> list[date]:
        """Return activity dates for a student up to and including a date."""
        statement = (
            select(StudentDailyActivity.activity_date)
            .where(
                StudentDailyActivity.user_id == user_id,
                StudentDailyActivity.activity_date <= through_date,
            )
            .order_by(StudentDailyActivity.activity_date.desc())
        )
        result = await session.scalars(statement)
        return list(result)

    async def list_between(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        from_date: date,
        to_date: date,
    ) -> list[StudentDailyActivity]:
        """Return activity rows in ascending order for an inclusive date range."""
        statement = (
            select(StudentDailyActivity)
            .where(
                StudentDailyActivity.user_id == user_id,
                StudentDailyActivity.activity_date >= from_date,
                StudentDailyActivity.activity_date <= to_date,
            )
            .order_by(StudentDailyActivity.activity_date)
        )
        result = await session.scalars(statement)
        return list(result)
