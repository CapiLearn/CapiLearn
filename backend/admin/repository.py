from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.chat.models import Conversation, LLMCostComponent, Message
from backend.chat.schemas import MessageRole, MessageStatus
from backend.usage.repository import UserActivityAggregate, list_admin_user_activity


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
        (
            total_users,
            user_queries,
            assistant_responses,
            failed_responses,
            blocked_responses,
            average_latency_ms,
        ) = (await session.execute(message_statement)).one()

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
            total_users=int(total_users),
            total_conversations=int(total_conversations),
            user_queries=int(user_queries),
            assistant_responses=int(assistant_responses),
            failed_responses=int(failed_responses),
            blocked_responses=int(blocked_responses),
            total_tokens=int(total_tokens),
            estimated_cost_usd=Decimal(estimated_cost_usd),
            average_latency_ms=average_latency_ms,
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
            usage_day: {
                "user_queries": int(user_queries),
                "assistant_responses": int(assistant_responses),
            }
            for usage_day, user_queries, assistant_responses in rows
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
    ) -> list[UserActivityAggregate]:
        return await list_admin_user_activity(
            session,
            range_start=range_start,
            range_end=range_end,
            limit=limit,
            offset=offset,
        )


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
    for usage_day, total_tokens in component_rows:
        totals[usage_day] = totals.get(usage_day, 0) + int(total_tokens)
    return totals


def _utc_date(column):
    return cast(column.op("AT TIME ZONE")("UTC"), Date)
