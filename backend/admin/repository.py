from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.chat.models import Conversation, Message
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
            func.coalesce(func.sum(Message.total_tokens), 0),
            func.coalesce(func.sum(Message.estimated_cost_usd), Decimal("0")),
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

        return UsageMetricsAggregate(
            total_users=int(row[0] or 0),
            total_conversations=int(total_conversations or 0),
            user_queries=int(row[1] or 0),
            assistant_responses=int(row[2] or 0),
            failed_responses=int(row[3] or 0),
            blocked_responses=int(row[4] or 0),
            total_tokens=int(row[5] or 0),
            estimated_cost_usd=Decimal(row[6] or 0),
            average_latency_ms=row[7],
        )

    async def list_daily_usage(
        self,
        session: AsyncSession,
        *,
        range_start: datetime,
        range_end: datetime,
    ) -> list[DailyUsageAggregate]:
        usage_date = cast(Message.created_at.op("AT TIME ZONE")("UTC"), Date)
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
                func.coalesce(func.sum(Message.total_tokens), 0),
            )
            .where(
                Message.created_at >= range_start,
                Message.created_at < range_end,
            )
            .group_by(usage_date)
            .order_by(usage_date.asc())
        )

        rows = (await session.execute(statement)).all()
        return [
            DailyUsageAggregate(
                date=row[0],
                user_queries=int(row[1] or 0),
                assistant_responses=int(row[2] or 0),
                total_tokens=int(row[3] or 0),
            )
            for row in rows
        ]
