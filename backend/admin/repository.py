from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

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
class CostComponentAggregate:
    id: UUID
    user_id: UUID
    conversation_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID
    component_order: int
    component_type: str
    attempt_index: int
    provider: str | None
    configured_model: str | None
    response_model: str | None
    finish_reason: str | None
    status: str
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    estimated_cost_usd: Decimal | None
    latency_ms: int | None
    error_type: str | None
    metadata: dict
    created_at: datetime


@dataclass(frozen=True)
class UserOverviewAggregate:
    id: UUID
    clerk_id: str
    display_name: str
    email: str | None
    access_level: str
    total_messages: int
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
        total_tokens = await _get_total_pipeline_tokens(
            session,
            range_start=range_start,
            range_end=range_end,
        )

        return UsageMetricsAggregate(
            total_users=int(row[0] or 0),
            total_conversations=int(total_conversations or 0),
            user_queries=int(row[1] or 0),
            assistant_responses=int(row[2] or 0),
            failed_responses=int(row[3] or 0),
            blocked_responses=int(row[4] or 0),
            total_tokens=total_tokens,
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
        token_totals = await _list_daily_pipeline_tokens(
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

    async def list_cost_components(
        self,
        session: AsyncSession,
        *,
        range_start: datetime,
        range_end: datetime,
        conversation_id: UUID | None = None,
        assistant_message_id: UUID | None = None,
        component_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CostComponentAggregate]:
        statement = select(LLMCostComponent).where(
            LLMCostComponent.created_at >= range_start,
            LLMCostComponent.created_at < range_end,
        )
        if conversation_id is not None:
            statement = statement.where(LLMCostComponent.conversation_id == conversation_id)
        if assistant_message_id is not None:
            statement = statement.where(
                LLMCostComponent.assistant_message_id == assistant_message_id
            )
        if component_type is not None:
            statement = statement.where(LLMCostComponent.component_type == component_type)
        statement = (
            statement.order_by(
                LLMCostComponent.created_at.asc(),
                LLMCostComponent.component_order.asc(),
            )
            .offset(offset)
            .limit(limit)
        )

        rows = (await session.scalars(statement)).all()
        return [
            CostComponentAggregate(
                id=row.id,
                user_id=row.user_id,
                conversation_id=row.conversation_id,
                user_message_id=row.user_message_id,
                assistant_message_id=row.assistant_message_id,
                component_order=row.component_order,
                component_type=row.component_type,
                attempt_index=row.attempt_index,
                provider=row.provider,
                configured_model=row.configured_model,
                response_model=row.response_model,
                finish_reason=row.finish_reason,
                status=row.status,
                prompt_tokens=row.prompt_tokens,
                completion_tokens=row.completion_tokens,
                total_tokens=row.total_tokens,
                estimated_cost_usd=row.estimated_cost_usd,
                latency_ms=row.latency_ms,
                error_type=row.error_type,
                metadata=row.extra_metadata or {},
                created_at=row.created_at,
            )
            for row in rows
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
        total_messages = func.count(Message.id).label("total_messages")
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
                total_messages,
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
                UserAccount.id,
                UserAccount.clerk_id,
                UserAccount.display_name,
                UserAccount.email,
                UserAccount.role.label("access_level"),
                activity.c.total_messages,
                activity.c.blocked_requests,
                activity.c.last_activity,
            )
            .select_from(UserAccount)
            .outerjoin(activity, activity.c.user_id == UserAccount.id)
            .where(UserAccount.deleted_at.is_(None))
            .order_by(
                activity.c.last_activity.desc().nulls_last(),
                UserAccount.display_name.asc(),
                UserAccount.email.asc().nulls_last(),
                UserAccount.clerk_id.asc(),
                UserAccount.id.asc(),
            )
            .offset(offset)
            .limit(limit)
        )

        rows = (await session.execute(statement)).all()
        return [
            UserOverviewAggregate(
                id=row.id,
                clerk_id=row.clerk_id,
                display_name=row.display_name,
                email=row.email,
                access_level=row.access_level,
                total_messages=int(row.total_messages or 0),
                blocked_requests=int(row.blocked_requests or 0),
                last_activity=row.last_activity,
            )
            for row in rows
        ]


async def _get_total_pipeline_tokens(
    session: AsyncSession,
    *,
    range_start: datetime,
    range_end: datetime,
) -> int:
    component_tokens = await session.scalar(
        select(func.coalesce(func.sum(LLMCostComponent.total_tokens), 0)).where(
            LLMCostComponent.created_at >= range_start,
            LLMCostComponent.created_at < range_end,
        )
    )
    legacy_tokens = await session.scalar(
        select(func.coalesce(func.sum(Message.total_tokens), 0)).where(
            Message.role == MessageRole.ASSISTANT.value,
            Message.created_at >= range_start,
            Message.created_at < range_end,
            ~_message_has_cost_components(),
        )
    )
    return int(component_tokens or 0) + int(legacy_tokens or 0)


async def _list_daily_pipeline_tokens(
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

    legacy_date = _utc_date(Message.created_at)
    legacy_statement = (
        select(
            legacy_date.label("usage_date"),
            func.coalesce(func.sum(Message.total_tokens), 0),
        )
        .where(
            Message.role == MessageRole.ASSISTANT.value,
            Message.created_at >= range_start,
            Message.created_at < range_end,
            ~_message_has_cost_components(),
        )
        .group_by(legacy_date)
    )
    legacy_rows = (await session.execute(legacy_statement)).all()

    totals: dict[date, int] = {}
    for row in [*component_rows, *legacy_rows]:
        totals[row[0]] = totals.get(row[0], 0) + int(row[1] or 0)
    return totals


def _message_has_cost_components():
    return (
        select(LLMCostComponent.id)
        .where(LLMCostComponent.assistant_message_id == Message.id)
        .exists()
    )


def _utc_date(column):
    return cast(column.op("AT TIME ZONE")("UTC"), Date)
