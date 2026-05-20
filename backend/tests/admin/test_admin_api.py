from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from backend.admin.dependencies import get_admin_usage_service
from backend.admin.repository import UsageMetricsAggregate
from backend.admin.schemas import AdminUsageSummaryResponse, UsageMetrics, UsageRange
from backend.admin.service import AdminUsageService
from backend.main import app


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_admin_openapi_exposes_usage_summary_route() -> None:
    schema = app.openapi()

    assert "/api/admin/usage/summary" in schema["paths"]
    assert (
        schema["paths"]["/api/admin/usage/summary"]["get"]["operationId"] == "getAdminUsageSummary"
    )


@pytest.mark.asyncio
async def test_usage_summary_requires_admin_header() -> None:
    app.dependency_overrides[get_admin_usage_service] = lambda: FakeAdminUsageService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        missing_response = await client.get("/api/admin/usage/summary")
        false_response = await client.get(
            "/api/admin/usage/summary",
            headers={"X-Admin-User": "false"},
        )

    expected = {
        "code": "admin_required",
        "message": "Admin access is required.",
        "details": None,
    }
    assert missing_response.status_code == 401
    assert missing_response.json() == expected
    assert false_response.status_code == 401
    assert false_response.json() == expected


@pytest.mark.asyncio
async def test_usage_summary_accepts_normalized_true_admin_header() -> None:
    app.dependency_overrides[get_admin_usage_service] = lambda: FakeAdminUsageService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/admin/usage/summary",
            headers={"X-Admin-User": " TRUE "},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["range"] == {
        "fromDate": "2026-05-01",
        "toDate": "2026-05-04",
    }
    assert payload["metrics"]["estimatedCostUsd"] == "1.284500"
    assert payload["dailyUsage"] == []


@pytest.mark.asyncio
async def test_usage_summary_rejects_invalid_date_ranges() -> None:
    app.dependency_overrides[get_admin_usage_service] = lambda: AdminUsageService(
        session=object(),
        repository=EmptyUsageRepository(),
        clock=lambda: datetime(2026, 5, 19, 12, tzinfo=UTC),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/admin/usage/summary?fromDate=2026-05-01&toDate=2026-05-01",
            headers={"X-Admin-User": "true"},
        )

    assert response.status_code == 400
    assert response.json() == {
        "code": "invalid_date_range",
        "message": "Usage summary ranges must use UTC calendar dates and span at least one day.",
        "details": {
            "fromDate": "2026-05-01",
            "toDate": "2026-05-01",
        },
    }


@pytest.mark.asyncio
async def test_usage_summary_defaults_to_last_seven_utc_calendar_days() -> None:
    repository = EmptyUsageRepository()
    app.dependency_overrides[get_admin_usage_service] = lambda: AdminUsageService(
        session=object(),
        repository=repository,
        clock=lambda: datetime(2026, 5, 19, 12, tzinfo=UTC),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/admin/usage/summary",
            headers={"X-Admin-User": "true"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["range"] == {
        "fromDate": "2026-05-13",
        "toDate": "2026-05-20",
    }
    assert [point["date"] for point in payload["dailyUsage"]] == [
        "2026-05-13",
        "2026-05-14",
        "2026-05-15",
        "2026-05-16",
        "2026-05-17",
        "2026-05-18",
        "2026-05-19",
    ]


class FakeAdminUsageService:
    async def get_usage_summary(
        self,
        *,
        from_date: str | None,
        to_date: str | None,
    ) -> AdminUsageSummaryResponse:
        return AdminUsageSummaryResponse(
            range=UsageRange(
                from_date="2026-05-01",
                to_date="2026-05-04",
            ),
            metrics=UsageMetrics(
                total_users=18,
                total_conversations=47,
                user_queries=142,
                assistant_responses=139,
                failed_responses=3,
                blocked_responses=4,
                total_tokens=89321,
                estimated_cost_usd="1.284500",
                average_latency_ms=1830,
            ),
            daily_usage=[],
        )


class EmptyUsageRepository:
    async def get_usage_metrics(self, session, *, range_start, range_end):
        return UsageMetricsAggregate(
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

    async def list_daily_usage(self, session, *, range_start, range_end):
        return []
