from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from backend.admin.repository import (
    AdminUsageRepository,
    CostComponentAggregate,
    DailyUsageAggregate,
    UsageMetricsAggregate,
)
from backend.admin.service import AdminUsageService
from backend.core.exceptions import ApiError


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
async def test_list_cost_components_maps_granular_cost_rows() -> None:
    component = CostComponentAggregate(
        id=uuid4(),
        user_id=uuid4(),
        conversation_id=uuid4(),
        user_message_id=uuid4(),
        assistant_message_id=uuid4(),
        component_order=2,
        component_type="output_guardrail",
        attempt_index=1,
        provider="openai",
        configured_model="openai/gpt-4o-mini",
        response_model="gpt-4o-mini-2024-07-18",
        finish_reason="stop",
        status="completed",
        prompt_tokens=10,
        completion_tokens=2,
        total_tokens=12,
        estimated_cost_usd=Decimal("0.000000123456"),
        latency_ms=44,
        error_type=None,
        metadata={"checkType": "output"},
        created_at=datetime(2026, 5, 1, 12, tzinfo=UTC),
    )
    repository = CapturingUsageRepository(cost_components=[component])
    service = AdminUsageService(
        session=object(),
        repository=repository,
        clock=lambda: datetime(2026, 5, 19, 12, tzinfo=UTC),
    )

    response = await service.list_cost_components(
        from_date="2026-05-01",
        to_date="2026-05-02",
        conversation_id=component.conversation_id,
        assistant_message_id=component.assistant_message_id,
        component_type="output_guardrail",
        limit=25,
        offset=50,
    )

    assert repository.conversation_id == component.conversation_id
    assert repository.assistant_message_id == component.assistant_message_id
    assert repository.component_type == "output_guardrail"
    assert repository.limit == 25
    assert repository.offset == 50
    assert response.cost_components[0].estimated_cost_usd == "0.000000123456"
    assert response.cost_components[0].component_type == "output_guardrail"


@pytest.mark.asyncio
async def test_cost_component_repository_applies_limit_and_offset() -> None:
    session = CapturingScalarSession()
    repository = AdminUsageRepository()

    rows = await repository.list_cost_components(
        session,
        range_start=datetime(2026, 5, 1, tzinfo=UTC),
        range_end=datetime(2026, 5, 2, tzinfo=UTC),
        limit=25,
        offset=50,
    )

    assert rows == []
    assert session.statement is not None
    assert session.statement._limit_clause.value == 25
    assert session.statement._offset_clause.value == 50


@pytest.mark.asyncio
async def test_usage_metrics_uses_component_tokens() -> None:
    session = SequencedSession(
        execute_results=[
            [
                (
                    2,
                    5,
                    4,
                    1,
                    2,
                    Decimal("1830.2"),
                )
            ],
        ],
        scalar_results=[
            3,
            Decimal("1.2"),
            12,
        ],
    )
    repository = AdminUsageRepository()

    metrics = await repository.get_usage_metrics(
        session,
        range_start=datetime(2026, 5, 1, tzinfo=UTC),
        range_end=datetime(2026, 5, 2, tzinfo=UTC),
    )

    assert metrics.total_users == 2
    assert metrics.total_conversations == 3
    assert metrics.user_queries == 5
    assert metrics.assistant_responses == 4
    assert metrics.failed_responses == 1
    assert metrics.blocked_responses == 2
    assert metrics.total_tokens == 12
    assert metrics.estimated_cost_usd == Decimal("1.2")
    assert metrics.average_latency_ms == Decimal("1830.2")
    assert len(session.scalar_statements) == 3


@pytest.mark.asyncio
async def test_daily_usage_uses_component_tokens_and_zeroes_nulls() -> None:
    session = SequencedSession(
        execute_results=[
            [
                (date(2026, 5, 1), 2, 1),
                (date(2026, 5, 2), 0, 1),
            ],
            [
                (date(2026, 5, 1), 12),
                (date(2026, 5, 3), 5),
                (date(2026, 5, 4), None),
            ],
        ],
    )
    repository = AdminUsageRepository()

    daily_usage = await repository.list_daily_usage(
        session,
        range_start=datetime(2026, 5, 1, tzinfo=UTC),
        range_end=datetime(2026, 5, 5, tzinfo=UTC),
    )

    assert daily_usage == [
        DailyUsageAggregate(
            date=date(2026, 5, 1),
            user_queries=2,
            assistant_responses=1,
            total_tokens=12,
        ),
        DailyUsageAggregate(
            date=date(2026, 5, 2),
            user_queries=0,
            assistant_responses=1,
            total_tokens=0,
        ),
        DailyUsageAggregate(
            date=date(2026, 5, 3),
            user_queries=0,
            assistant_responses=0,
            total_tokens=5,
        ),
        DailyUsageAggregate(
            date=date(2026, 5, 4),
            user_queries=0,
            assistant_responses=0,
            total_tokens=0,
        ),
    ]
    assert len(session.execute_statements) == 2


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
        cost_components: list[CostComponentAggregate] | None = None,
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
        self.cost_components = cost_components or []
        self.range_start = None
        self.range_end = None
        self.conversation_id = None
        self.assistant_message_id = None
        self.component_type = None
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

    async def list_cost_components(
        self,
        session,
        *,
        range_start,
        range_end,
        conversation_id=None,
        assistant_message_id=None,
        component_type=None,
        limit=100,
        offset=0,
    ):
        self.range_start = range_start
        self.range_end = range_end
        self.conversation_id = conversation_id
        self.assistant_message_id = assistant_message_id
        self.component_type = component_type
        self.limit = limit
        self.offset = offset
        return self.cost_components


class CapturingScalarSession:
    def __init__(self) -> None:
        self.statement = None

    async def scalars(self, statement):
        self.statement = statement
        return EmptyScalarResult()


class EmptyScalarResult:
    def all(self):
        return []


class SequencedSession:
    def __init__(
        self,
        *,
        execute_results: list[list[tuple]] | None = None,
        scalar_results: list | None = None,
    ) -> None:
        self.execute_results = execute_results or []
        self.scalar_results = scalar_results or []
        self.execute_statements = []
        self.scalar_statements = []

    async def execute(self, statement):
        self.execute_statements.append(statement)
        return SequencedExecuteResult(self.execute_results.pop(0))

    async def scalar(self, statement):
        self.scalar_statements.append(statement)
        return self.scalar_results.pop(0)


class SequencedExecuteResult:
    def __init__(self, rows: list[tuple]) -> None:
        self.rows = rows

    def one(self):
        return self.rows[0]

    def all(self):
        return self.rows
