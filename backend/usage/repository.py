from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.models import UserAccount
from backend.chat.models import Message
from backend.chat.schemas import MessageRole, MessageStatus


@dataclass(frozen=True)
class UserActivityAggregate:
    display_name: str
    access_level: str
    total_messages_sent: int
    blocked_requests: int
    last_activity: datetime | None


async def list_admin_user_activity(
    session: AsyncSession,
    *,
    range_start: datetime,
    range_end: datetime,
    limit: int = 100,
    offset: int = 0,
) -> list[UserActivityAggregate]:
    activity = _user_activity_subquery(range_start=range_start, range_end=range_end)
    statement = (
        _user_activity_select(activity)
        .where(UserAccount.deleted_at.is_(None))
        .order_by(
            activity.c.last_activity.desc().nulls_last(),
            UserAccount.first_name.asc().nulls_last(),
            UserAccount.last_name.asc().nulls_last(),
            UserAccount.clerk_id.asc(),
            UserAccount.id.asc(),
        )
        .offset(offset)
        .limit(limit)
    )
    rows = (await session.execute(statement)).all()
    return _activity_rows_to_aggregates(rows)


async def list_student_roster_activity(
    session: AsyncSession,
    *,
    range_start: datetime,
    range_end: datetime,
    limit: int = 100,
) -> list[UserActivityAggregate]:
    activity = _user_activity_subquery(range_start=range_start, range_end=range_end)
    statement = (
        _user_activity_select(activity)
        .where(
            UserAccount.deleted_at.is_(None),
            UserAccount.role == "student",
        )
        .order_by(
            UserAccount.last_name.asc(),
            UserAccount.first_name.asc(),
            UserAccount.id.asc(),
        )
        .limit(limit)
    )
    rows = (await session.execute(statement)).all()
    return _activity_rows_to_aggregates(rows)


def _user_activity_subquery(*, range_start: datetime, range_end: datetime):
    last_activity = func.max(Message.created_at).label("last_activity")
    total_messages_sent = func.coalesce(
        func.sum(case((Message.role == MessageRole.USER.value, 1), else_=0)),
        0,
    ).label("total_messages_sent")
    blocked_requests = func.coalesce(
        func.sum(
            case(
                (
                    (Message.role == MessageRole.ASSISTANT.value)
                    & (Message.status == MessageStatus.BLOCKED.value),
                    1,
                ),
                else_=0,
            )
        ),
        0,
    ).label("blocked_requests")

    activity = (
        select(
            Message.user_id.label("user_id"),
            total_messages_sent,
            blocked_requests,
            last_activity,
        )
        .where(
            Message.created_at >= range_start,
            Message.created_at < range_end,
        )
        .group_by(Message.user_id)
        .subquery()
    )
    return activity


def _user_activity_select(activity):
    return (
        select(
            UserAccount.first_name,
            UserAccount.last_name,
            UserAccount.role.label("access_level"),
            activity.c.total_messages_sent,
            activity.c.blocked_requests,
            activity.c.last_activity,
        )
        .select_from(UserAccount)
        .outerjoin(activity, activity.c.user_id == UserAccount.id)
    )


def _activity_rows_to_aggregates(rows) -> list[UserActivityAggregate]:
    return [
        UserActivityAggregate(
            display_name=f"{row.first_name} {row.last_name}",
            access_level=row.access_level,
            total_messages_sent=int(row.total_messages_sent or 0),
            blocked_requests=int(row.blocked_requests or 0),
            last_activity=row.last_activity,
        )
        for row in rows
    ]
