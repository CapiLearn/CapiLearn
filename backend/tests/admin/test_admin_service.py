from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from backend.admin.repository import (
    DailyUsageAggregate,
    UsageMetricsAggregate,
)
from backend.admin.service import AdminUsageService
from backend.core.exceptions import ApiError
from backend.usage.repository import UserActivityAggregate


@pytest.mark.asyncio
async def test_usage_summary_maps_metrics_and_zero_fills_daily_usage() -> None:
    repository = CapturingUsageRepository(
        metrics=UsageMetricsAggregate(
            total_users=2,
            total_conversations=3,
            user_queries=5,
            assistant_responses=4,
            failed_responses=1,
            blocked_responses=2,
            total_tokens=99,
            estimated_cost_usd=Decimal("1.2"),
            average_latency_ms=Decimal("1830.2"),
        ),
        daily_usage=[
            DailyUsageAggregate(
                date=date(2026, 5, 1),
                user_queries=2,
                assistant_responses=1,
                total_tokens=20,
            ),
            DailyUsageAggregate(
                date=date(2026, 5, 3),
                user_queries=3,
                assistant_responses=3,
                total_tokens=79,
            ),
        ],
    )
    service = AdminUsageService(
        session=object(),
        repository=repository,
        clock=lambda: datetime(2026, 5, 19, 12, tzinfo=UTC),
    )

    response = await service.get_usage_summary(
        from_date="2026-05-01",
        to_date="2026-05-04",
    )

    assert repository.range_start == datetime(2026, 5, 1, tzinfo=UTC)
    assert repository.range_end == datetime(2026, 5, 4, tzinfo=UTC)
    assert response.model_dump(mode="json", by_alias=True) == {
        "range": {
            "fromDate": "2026-05-01",
            "toDate": "2026-05-04",
        },
        "metrics": {
            "totalUsers": 2,
            "totalConversations": 3,
            "userQueries": 5,
            "assistantResponses": 4,
            "failedResponses": 1,
            "blockedResponses": 2,
            "totalTokens": 99,
            "estimatedCostUsd": "1.200000",
            "averageLatencyMs": 1830,
        },
        "dailyUsage": [
            {
                "date": "2026-05-01",
                "userQueries": 2,
                "assistantResponses": 1,
                "totalTokens": 20,
            },
            {
                "date": "2026-05-02",
                "userQueries": 0,
                "assistantResponses": 0,
                "totalTokens": 0,
            },
            {
                "date": "2026-05-03",
                "userQueries": 3,
                "assistantResponses": 3,
                "totalTokens": 79,
            },
        ],
    }


@pytest.mark.asyncio
async def test_usage_summary_returns_null_latency_when_no_latency_data_exists() -> None:
    service = AdminUsageService(
        session=object(),
        repository=CapturingUsageRepository(
            metrics=UsageMetricsAggregate(
                total_users=0,
                total_conversations=0,
                user_queries=0,
                assistant_responses=0,
                failed_responses=0,
                blocked_responses=0,
                total_tokens=0,
                estimated_cost_usd=Decimal("0"),
                average_latency_ms=None,
            ),
            daily_usage=[],
        ),
        clock=lambda: datetime(2026, 5, 19, 12, tzinfo=UTC),
    )

    response = await service.get_usage_summary(
        from_date="2026-05-01",
        to_date="2026-05-02",
    )

    assert response.metrics.estimated_cost_usd == "0.000000"
    assert response.metrics.average_latency_ms is None


@pytest.mark.asyncio
async def test_list_user_overviews_maps_rows_and_forwards_range_limit_offset() -> None:
    last_activity = datetime(2026, 5, 2, 16, 30, tzinfo=UTC)
    aggregate = UserActivityAggregate(
        display_name="Student Demo",
        access_level="student",
        total_messages_sent=3,
        blocked_requests=1,
        last_activity=last_activity,
    )
    repository = CapturingUsageRepository(user_overviews=[aggregate])
    service = AdminUsageService(
        session=object(),
        repository=repository,
        clock=lambda: datetime(2026, 5, 19, 12, tzinfo=UTC),
    )

    response = await service.list_user_overviews(
        from_date="2026-05-01",
        to_date="2026-05-03",
        limit=25,
        offset=50,
    )

    assert repository.range_start == datetime(2026, 5, 1, tzinfo=UTC)
    assert repository.range_end == datetime(2026, 5, 3, tzinfo=UTC)
    assert repository.limit == 25
    assert repository.offset == 50
    assert response.users[0].display_name == "Student Demo"
    assert response.users[0].total_messages_sent == 3
    assert response.users[0].blocked_requests == 1
    assert response.users[0].last_activity == last_activity


@pytest.mark.asyncio
async def test_usage_summary_rejects_non_iso_calendar_dates() -> None:
    service = AdminUsageService(
        session=object(),
        repository=CapturingUsageRepository(),
        clock=lambda: datetime(2026, 5, 19, 12, tzinfo=UTC),
    )

    with pytest.raises(ApiError) as exc_info:
        await service.get_usage_summary(
            from_date="2026-5-01",
            to_date="2026-05-02",
        )

    assert exc_info.value.code == "invalid_date_range"
    assert exc_info.value.details == {
        "fromDate": "2026-5-01",
        "toDate": "2026-05-02",
    }


@pytest.mark.asyncio
async def test_usage_summary_allows_maximum_366_day_range() -> None:
    repository = CapturingUsageRepository()
    service = AdminUsageService(
        session=object(),
        repository=repository,
        clock=lambda: datetime(2026, 5, 19, 12, tzinfo=UTC),
    )

    response = await service.get_usage_summary(
        from_date="2025-01-01",
        to_date="2026-01-02",
    )

    assert repository.range_start == datetime(2025, 1, 1, tzinfo=UTC)
    assert repository.range_end == datetime(2026, 1, 2, tzinfo=UTC)
    assert len(response.daily_usage) == 366


@pytest.mark.asyncio
async def test_usage_summary_rejects_ranges_over_366_days_before_querying() -> None:
    repository = CapturingUsageRepository()
    service = AdminUsageService(
        session=object(),
        repository=repository,
        clock=lambda: datetime(2026, 5, 19, 12, tzinfo=UTC),
    )

    with pytest.raises(ApiError) as exc_info:
        await service.get_usage_summary(
            from_date="2025-01-01",
            to_date="2026-01-03",
        )

    assert exc_info.value.code == "date_range_too_large"
    assert exc_info.value.details == {
        "fromDate": "2025-01-01",
        "toDate": "2026-01-03",
        "maxDays": 366,
    }
    assert repository.range_start is None
    assert repository.range_end is None


class CapturingUsageRepository:
    def __init__(
        self,
        *,
        metrics: UsageMetricsAggregate | None = None,
        daily_usage: list[DailyUsageAggregate] | None = None,
        user_overviews: list[UserActivityAggregate] | None = None,
    ) -> None:
        self.metrics = metrics or UsageMetricsAggregate(
            total_users=0,
            total_conversations=0,
            user_queries=0,
            assistant_responses=0,
            failed_responses=0,
            blocked_responses=0,
            total_tokens=0,
            estimated_cost_usd=Decimal("0"),
            average_latency_ms=None,
        )
        self.daily_usage = daily_usage or []
        self.user_overviews = user_overviews or []
        self.range_start = None
        self.range_end = None
        self.limit = None
        self.offset = None

    async def get_usage_metrics(self, session, *, range_start, range_end):
        self.range_start = range_start
        self.range_end = range_end
        return self.metrics

    async def list_daily_usage(self, session, *, range_start, range_end):
        self.range_start = range_start
        self.range_end = range_end
        return self.daily_usage

    async def list_user_overviews(
        self,
        session,
        *,
        range_start,
        range_end,
        limit=100,
        offset=0,
    ):
        self.range_start = range_start
        self.range_end = range_end
        self.limit = limit
        self.offset = offset
        return self.user_overviews
