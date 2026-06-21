from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.activity.models import StudentDailyActivity
from backend.auth.models import UserAccount
from backend.auth.schemas import UserRole
from backend.chat.models import Message
from backend.chat.schemas import MessageRole
from backend.usage.repository import UserActivityAggregate, list_student_roster_activity


@dataclass(frozen=True)
class InstructorSummaryAggregate:
    active_students: int
    questions_asked: int


class InstructorDashboardRepository:
    async def get_summary_metrics(
        self,
        session: AsyncSession,
        *,
        range_start: datetime,
        range_end: datetime,
        activity_from_date: date,
        activity_to_date: date,
    ) -> InstructorSummaryAggregate:
        message_activity_exists = (
            select(Message.id)
            .where(
                Message.user_id == UserAccount.id,
                Message.role == MessageRole.USER.value,
                Message.created_at >= range_start,
                Message.created_at < range_end,
            )
            .exists()
        )
        daily_activity_exists = (
            select(StudentDailyActivity.id)
            .where(
                StudentDailyActivity.user_id == UserAccount.id,
                StudentDailyActivity.activity_date >= activity_from_date,
                StudentDailyActivity.activity_date < activity_to_date,
            )
            .exists()
        )
        active_students = await session.scalar(
            select(func.count(UserAccount.id)).where(
                UserAccount.role == UserRole.STUDENT.value,
                UserAccount.deleted_at.is_(None),
                or_(message_activity_exists, daily_activity_exists),
            )
        )

        questions_asked = await session.scalar(
            select(func.count(Message.id))
            .join(UserAccount, UserAccount.id == Message.user_id)
            .where(
                Message.role == MessageRole.USER.value,
                Message.created_at >= range_start,
                Message.created_at < range_end,
                UserAccount.role == UserRole.STUDENT.value,
                UserAccount.deleted_at.is_(None),
            )
        )

        return InstructorSummaryAggregate(
            active_students=int(active_students or 0),
            questions_asked=int(questions_asked or 0),
        )

    async def list_student_roster(
        self,
        session: AsyncSession,
        *,
        range_start: datetime,
        range_end: datetime,
        limit: int = 100,
    ) -> list[UserActivityAggregate]:
        return await list_student_roster_activity(
            session,
            range_start=range_start,
            range_end=range_end,
            limit=limit,
        )
