from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.admin.repository import AdminUsageRepository, DailyUsageAggregate
from backend.admin.schemas import (
    AdminUsageSummaryResponse,
    AdminUserOverview,
    AdminUserOverviewResponse,
    DailyUsagePoint,
    UsageMetrics,
    UsageRange,
    format_cost,
)
from backend.core.date_ranges import DateWindow, resolve_date_window

DATE_RANGE_ERROR = "Usage summary ranges must use UTC calendar dates and span at least one day."
MAX_USAGE_RANGE_DAYS = 366


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
                from_date=usage_window.from_date,
                to_date=usage_window.to_date,
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
                from_date=usage_window.from_date,
                to_date=usage_window.to_date,
                aggregates=daily_usage,
            ),
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

    def _resolve_window(self, *, from_date: str | None, to_date: str | None) -> DateWindow:
        return resolve_date_window(
            from_date,
            to_date,
            clock=self._clock,
            timezone=UTC,
            max_days=MAX_USAGE_RANGE_DAYS,
            invalid_message=DATE_RANGE_ERROR,
            too_large_message=f"Usage summary ranges cannot exceed {MAX_USAGE_RANGE_DAYS} days.",
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
