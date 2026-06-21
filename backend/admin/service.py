import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.admin.repository import AdminUsageRepository, DailyUsageAggregate
from backend.admin.schemas import (
    AdminUsageSummaryResponse,
    AdminUserOverview,
    AdminUserOverviewResponse,
    CostComponentResponse,
    CostComponentsResponse,
    DailyUsagePoint,
    UsageMetrics,
    UsageRange,
    format_component_cost,
    format_cost,
)
from backend.core.exceptions import ApiError

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATE_RANGE_ERROR = "Usage summary ranges must use UTC calendar dates and span at least one day."
MAX_USAGE_RANGE_DAYS = 366


@dataclass(frozen=True)
class ResolvedUsageWindow:
    usage_range: UsageRange
    range_start: datetime
    range_end: datetime


class AdminUsageService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        repository: AdminUsageRepository | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session = session
        self._repository = repository or AdminUsageRepository()
        self._clock = clock or (lambda: datetime.now(UTC))

    async def get_usage_summary(
        self,
        *,
        from_date: str | None,
        to_date: str | None,
    ) -> AdminUsageSummaryResponse:
        usage_window = self._resolve_window(from_date=from_date, to_date=to_date)

        metrics = await self._repository.get_usage_metrics(
            self._session,
            range_start=usage_window.range_start,
            range_end=usage_window.range_end,
        )
        daily_usage = await self._repository.list_daily_usage(
            self._session,
            range_start=usage_window.range_start,
            range_end=usage_window.range_end,
        )

        return AdminUsageSummaryResponse(
            range=UsageRange(
                from_date=usage_window.usage_range.from_date,
                to_date=usage_window.usage_range.to_date,
            ),
            metrics=UsageMetrics(
                total_users=metrics.total_users,
                total_conversations=metrics.total_conversations,
                user_queries=metrics.user_queries,
                assistant_responses=metrics.assistant_responses,
                failed_responses=metrics.failed_responses,
                blocked_responses=metrics.blocked_responses,
                total_tokens=metrics.total_tokens,
                estimated_cost_usd=format_cost(metrics.estimated_cost_usd),
                average_latency_ms=_rounded_latency(metrics.average_latency_ms),
            ),
            daily_usage=_fill_daily_usage(
                from_date=usage_window.usage_range.from_date,
                to_date=usage_window.usage_range.to_date,
                aggregates=daily_usage,
            ),
        )

    async def list_cost_components(
        self,
        *,
        from_date: str | None,
        to_date: str | None,
        conversation_id: UUID | None = None,
        assistant_message_id: UUID | None = None,
        component_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> CostComponentsResponse:
        usage_window = self._resolve_window(from_date=from_date, to_date=to_date)
        components = await self._repository.list_cost_components(
            self._session,
            range_start=usage_window.range_start,
            range_end=usage_window.range_end,
            conversation_id=conversation_id,
            assistant_message_id=assistant_message_id,
            component_type=component_type,
            limit=limit,
            offset=offset,
        )
        return CostComponentsResponse(
            range=UsageRange(
                from_date=usage_window.usage_range.from_date,
                to_date=usage_window.usage_range.to_date,
            ),
            cost_components=[
                CostComponentResponse(
                    id=component.id,
                    user_id=component.user_id,
                    conversation_id=component.conversation_id,
                    user_message_id=component.user_message_id,
                    assistant_message_id=component.assistant_message_id,
                    component_order=component.component_order,
                    component_type=component.component_type,
                    attempt_index=component.attempt_index,
                    provider=component.provider,
                    configured_model=component.configured_model,
                    response_model=component.response_model,
                    finish_reason=component.finish_reason,
                    status=component.status,
                    prompt_tokens=component.prompt_tokens,
                    completion_tokens=component.completion_tokens,
                    total_tokens=component.total_tokens,
                    estimated_cost_usd=format_component_cost(component.estimated_cost_usd),
                    latency_ms=component.latency_ms,
                    error_type=component.error_type,
                    metadata=component.metadata,
                    created_at=component.created_at,
                )
                for component in components
            ],
        )

    async def list_user_overviews(
        self,
        *,
        from_date: str | None,
        to_date: str | None,
        limit: int = 100,
        offset: int = 0,
    ) -> AdminUserOverviewResponse:
        usage_window = self._resolve_window(from_date=from_date, to_date=to_date)
        users = await self._repository.list_user_overviews(
            self._session,
            range_start=usage_window.range_start,
            range_end=usage_window.range_end,
            limit=limit,
            offset=offset,
        )
        return AdminUserOverviewResponse(
            users=[
                AdminUserOverview(
                    display_name=user.display_name,
                    access_level=user.access_level,
                    total_messages_sent=user.total_messages_sent,
                    blocked_requests=user.blocked_requests,
                    last_activity=user.last_activity,
                )
                for user in users
            ],
        )

    def _resolve_window(self, *, from_date: str | None, to_date: str | None) -> ResolvedUsageWindow:
        usage_range = self._resolve_range(from_date=from_date, to_date=to_date)
        return ResolvedUsageWindow(
            usage_range=usage_range,
            range_start=datetime.combine(usage_range.from_date, time.min, tzinfo=UTC),
            range_end=datetime.combine(usage_range.to_date, time.min, tzinfo=UTC),
        )

    def _resolve_range(self, *, from_date: str | None, to_date: str | None) -> UsageRange:
        resolved_to_date = (
            _parse_date(to_date, from_date=from_date, to_date=to_date)
            if to_date is not None
            else self._clock().astimezone(UTC).date() + timedelta(days=1)
        )
        resolved_from_date = (
            _parse_date(from_date, from_date=from_date, to_date=to_date)
            if from_date is not None
            else resolved_to_date - timedelta(days=7)
        )

        if resolved_to_date <= resolved_from_date:
            raise _invalid_date_range(from_date=from_date, to_date=to_date)

        if (resolved_to_date - resolved_from_date).days > MAX_USAGE_RANGE_DAYS:
            raise ApiError(
                code="date_range_too_large",
                message=f"Usage summary ranges cannot exceed {MAX_USAGE_RANGE_DAYS} days.",
                details={
                    "fromDate": from_date,
                    "toDate": to_date,
                    "maxDays": MAX_USAGE_RANGE_DAYS,
                },
            )

        return UsageRange(from_date=resolved_from_date, to_date=resolved_to_date)


def _parse_date(value: str, *, from_date: str | None, to_date: str | None) -> date:
    if not DATE_PATTERN.fullmatch(value):
        raise _invalid_date_range(from_date=from_date, to_date=to_date)

    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise _invalid_date_range(from_date=from_date, to_date=to_date) from exc


def _invalid_date_range(*, from_date: str | None, to_date: str | None) -> ApiError:
    return ApiError(
        code="invalid_date_range",
        message=DATE_RANGE_ERROR,
        details={
            "fromDate": from_date,
            "toDate": to_date,
        },
    )


def _rounded_latency(value: Decimal | float | None) -> int | None:
    if value is None:
        return None
    return int(round(float(value)))


def _fill_daily_usage(
    *,
    from_date: date,
    to_date: date,
    aggregates: list[DailyUsageAggregate],
) -> list[DailyUsagePoint]:
    by_date = {aggregate.date: aggregate for aggregate in aggregates}
    points = []
    current = from_date
    while current < to_date:
        aggregate = by_date.get(current)
        points.append(
            DailyUsagePoint(
                date=current,
                user_queries=aggregate.user_queries if aggregate else 0,
                assistant_responses=aggregate.assistant_responses if aggregate else 0,
                total_tokens=aggregate.total_tokens if aggregate else 0,
            )
        )
        current += timedelta(days=1)
    return points
