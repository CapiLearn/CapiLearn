from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.models import UserAccount
from backend.chat.models import Conversation, LLMCostComponent, Message
from backend.chat.schemas import MessageRole, MessageStatus


@dataclass(frozen=True)
class UsageMetricsAggregate:
    total_users: int
    total_conversations: int
    user_queries: int
    assistant_responses: int
    failed_responses: int
    blocked_responses: int
    total_tokens: int
    estimated_cost_usd: Decimal
    average_latency_ms: Decimal | float | None


@dataclass(frozen=True)
class DailyUsageAggregate:
    date: date
    user_queries: int
    assistant_responses: int
    total_tokens: int


@dataclass(frozen=True)
class UserOverviewAggregate:
    display_name: str
    access_level: str
    total_messages_sent: int
    blocked_requests: int
    last_activity: datetime | None


class AdminUsageRepository:
    async def get_usage_metrics(
        self,
        session: AsyncSession,
        *,
        range_start: datetime,
        range_end: datetime,
    ) -> UsageMetricsAggregate:
        message_statement = select(
            func.count(func.distinct(Message.user_id)),
            func.coalesce(
                func.sum(case((Message.role == MessageRole.USER.value, 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(case((Message.role == MessageRole.ASSISTANT.value, 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            (Message.role == MessageRole.ASSISTANT.value)
                            & (Message.status == MessageStatus.FAILED.value),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
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
            ),
            func.avg(Message.latency_ms),
        ).where(
            Message.created_at >= range_start,
            Message.created_at < range_end,
        )
        row = (await session.execute(message_statement)).one()

        conversation_statement = select(func.count(Conversation.id)).where(
            Conversation.created_at >= range_start,
            Conversation.created_at < range_end,
        )
        total_conversations = await session.scalar(conversation_statement)

        cost_statement = select(
            func.coalesce(func.sum(LLMCostComponent.estimated_cost_usd), Decimal("0"))
        ).where(
            LLMCostComponent.created_at >= range_start,
            LLMCostComponent.created_at < range_end,
        )
        estimated_cost_usd = await session.scalar(cost_statement)
        total_tokens = await session.scalar(
            select(func.coalesce(func.sum(LLMCostComponent.total_tokens), 0)).where(
                LLMCostComponent.created_at >= range_start,
                LLMCostComponent.created_at < range_end,
            )
        )

        return UsageMetricsAggregate(
            total_users=int(row[0] or 0),
            total_conversations=int(total_conversations or 0),
            user_queries=int(row[1] or 0),
            assistant_responses=int(row[2] or 0),
            failed_responses=int(row[3] or 0),
            blocked_responses=int(row[4] or 0),
            total_tokens=int(total_tokens or 0),
            estimated_cost_usd=Decimal(estimated_cost_usd or 0),
            average_latency_ms=row[5],
        )

    async def list_daily_usage(
        self,
        session: AsyncSession,
        *,
        range_start: datetime,
        range_end: datetime,
    ) -> list[DailyUsageAggregate]:
        usage_date = _utc_date(Message.created_at)
        statement = (
            select(
                usage_date.label("usage_date"),
                func.coalesce(
                    func.sum(case((Message.role == MessageRole.USER.value, 1), else_=0)),
                    0,
                ),
                func.coalesce(
                    func.sum(case((Message.role == MessageRole.ASSISTANT.value, 1), else_=0)),
                    0,
                ),
            )
            .where(
                Message.created_at >= range_start,
                Message.created_at < range_end,
            )
            .group_by(usage_date)
            .order_by(usage_date.asc())
        )

        rows = (await session.execute(statement)).all()
        token_totals = await _list_daily_component_tokens(
            session,
            range_start=range_start,
            range_end=range_end,
        )
        message_counts = {
            row[0]: {
                "user_queries": int(row[1] or 0),
                "assistant_responses": int(row[2] or 0),
            }
            for row in rows
        }

        return [
            DailyUsageAggregate(
                date=usage_day,
                user_queries=message_counts.get(usage_day, {}).get("user_queries", 0),
                assistant_responses=message_counts.get(usage_day, {}).get(
                    "assistant_responses",
                    0,
                ),
                total_tokens=token_totals.get(usage_day, 0),
            )
            for usage_day in sorted(set(message_counts) | set(token_totals))
        ]

    async def list_user_overviews(
        self,
        session: AsyncSession,
        *,
        range_start: datetime,
        range_end: datetime,
        limit: int = 100,
        offset: int = 0,
    ) -> list[UserOverviewAggregate]:
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

        statement = (
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
        return [
            UserOverviewAggregate(
                display_name=f"{row.first_name} {row.last_name}",
                access_level=row.access_level,
                total_messages_sent=int(row.total_messages_sent or 0),
                blocked_requests=int(row.blocked_requests or 0),
                last_activity=row.last_activity,
            )
            for row in rows
        ]


async def _list_daily_component_tokens(
    session: AsyncSession,
    *,
    range_start: datetime,
    range_end: datetime,
) -> dict[date, int]:
    component_date = _utc_date(LLMCostComponent.created_at)
    component_statement = (
        select(
            component_date.label("usage_date"),
            func.coalesce(func.sum(LLMCostComponent.total_tokens), 0),
        )
        .where(
            LLMCostComponent.created_at >= range_start,
            LLMCostComponent.created_at < range_end,
        )
        .group_by(component_date)
    )
    component_rows = (await session.execute(component_statement)).all()

    totals: dict[date, int] = {}
    for row in component_rows:
        totals[row[0]] = totals.get(row[0], 0) + int(row[1] or 0)
    return totals


def _utc_date(column):
    return cast(column.op("AT TIME ZONE")("UTC"), Date)
