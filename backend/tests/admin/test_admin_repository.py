from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from backend.admin.repository import (
    AdminUsageRepository,
    DailyUsageAggregate,
)


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
async def test_daily_usage_uses_component_tokens_and_preserves_sparse_zeros() -> None:
    session = SequencedSession(
        execute_results=[
            [
                (date(2026, 5, 1), 2, 1),
                (date(2026, 5, 2), 0, 1),
            ],
            [
                (date(2026, 5, 1), 12),
                (date(2026, 5, 3), 5),
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
    ]
    assert len(session.execute_statements) == 2


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
