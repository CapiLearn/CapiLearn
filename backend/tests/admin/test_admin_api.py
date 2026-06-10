from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from backend.admin.dependencies import get_admin_health_service, get_admin_usage_service
from backend.admin.repository import UsageMetricsAggregate
from backend.admin.schemas import (
    AdminHealthCheck,
    AdminHealthResponse,
    AdminUsageSummaryResponse,
    CostComponentResponse,
    CostComponentsResponse,
    HealthStatus,
    UsageMetrics,
    UsageRange,
)
from backend.admin.service import AdminUsageService
from backend.main import app


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_admin_openapi_exposes_usage_summary_route() -> None:
    schema = app.openapi()

    assert "/api/admin/health" in schema["paths"]
    assert "/api/admin/usage/summary" in schema["paths"]
    assert "/api/admin/usage/cost-components" in schema["paths"]
    assert schema["paths"]["/api/admin/health"]["get"]["operationId"] == "getAdminHealth"
    assert (
        schema["paths"]["/api/admin/usage/summary"]["get"]["operationId"] == "getAdminUsageSummary"
    )
    assert (
        schema["paths"]["/api/admin/usage/cost-components"]["get"]["operationId"]
        == "listAdminUsageCostComponents"
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


@pytest.mark.asyncio
async def test_cost_components_endpoint_requires_admin_header() -> None:
    app.dependency_overrides[get_admin_usage_service] = lambda: FakeAdminUsageService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/admin/usage/cost-components")

    assert response.status_code == 401
    assert response.json()["code"] == "admin_required"


@pytest.mark.asyncio
async def test_cost_components_endpoint_returns_granular_rows() -> None:
    service = FakeAdminUsageService()
    app.dependency_overrides[get_admin_usage_service] = lambda: service

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/admin/usage/cost-components?fromDate=2026-05-01&toDate=2026-05-04"
            "&componentType=main_generation&limit=25&offset=50",
            headers={"X-Admin-User": "true"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["range"] == {
        "fromDate": "2026-05-01",
        "toDate": "2026-05-04",
    }
    assert payload["costComponents"][0]["componentType"] == "main_generation"
    assert payload["costComponents"][0]["estimatedCostUsd"] == "0.001000000000"
    assert service.limit == 25
    assert service.offset == 50


@pytest.mark.asyncio
async def test_cost_components_endpoint_rejects_limit_over_maximum() -> None:
    app.dependency_overrides[get_admin_usage_service] = lambda: FakeAdminUsageService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/admin/usage/cost-components?limit=501",
            headers={"X-Admin-User": "true"},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_admin_health_requires_admin_header() -> None:
    app.dependency_overrides[get_admin_health_service] = lambda: FakeAdminHealthService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/admin/health")

    assert response.status_code == 401
    assert response.json()["code"] == "admin_required"


@pytest.mark.asyncio
async def test_admin_health_returns_camel_case_response() -> None:
    app.dependency_overrides[get_admin_health_service] = lambda: FakeAdminHealthService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/admin/health",
            headers={"X-Admin-User": "true"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "degraded",
        "checkedAt": "2026-06-09T12:00:00Z",
        "checks": [
            {
                "name": "database",
                "status": "ok",
                "latencyMs": 8,
                "message": "Database connectivity check succeeded.",
                "details": {"backend": "postgres"},
            },
            {
                "name": "llmModelAccess",
                "status": "degraded",
                "latencyMs": None,
                "message": "Provider metadata returned no available models.",
                "details": {"returnedModelCount": 0},
            },
        ],
    }


class FakeAdminUsageService:
    def __init__(self) -> None:
        self.limit = None
        self.offset = None

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

    async def list_cost_components(
        self,
        *,
        from_date: str | None,
        to_date: str | None,
        conversation_id=None,
        assistant_message_id=None,
        component_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> CostComponentsResponse:
        self.limit = limit
        self.offset = offset
        return CostComponentsResponse(
            range=UsageRange(
                from_date=from_date or "2026-05-01",
                to_date=to_date or "2026-05-04",
            ),
            cost_components=[
                CostComponentResponse(
                    id=uuid4(),
                    user_id=uuid4(),
                    conversation_id=conversation_id or uuid4(),
                    user_message_id=uuid4(),
                    assistant_message_id=assistant_message_id or uuid4(),
                    component_order=1,
                    component_type=component_type or "main_generation",
                    attempt_index=1,
                    provider="openai",
                    configured_model="openai/gpt-4o-mini",
                    response_model="gpt-4o-mini",
                    finish_reason="stop",
                    status="completed",
                    prompt_tokens=4,
                    completion_tokens=5,
                    total_tokens=9,
                    estimated_cost_usd="0.001000000000",
                    latency_ms=120,
                    error_type=None,
                    metadata={},
                    created_at=datetime(2026, 5, 1, 12, tzinfo=UTC),
                )
            ],
        )


class FakeAdminHealthService:
    async def get_health(self) -> AdminHealthResponse:
        return AdminHealthResponse(
            status=HealthStatus.DEGRADED,
            checked_at=datetime(2026, 6, 9, 12, tzinfo=UTC),
            checks=[
                AdminHealthCheck(
                    name="database",
                    status=HealthStatus.OK,
                    latency_ms=8,
                    message="Database connectivity check succeeded.",
                    details={"backend": "postgres"},
                ),
                AdminHealthCheck(
                    name="llmModelAccess",
                    status=HealthStatus.DEGRADED,
                    message="Provider metadata returned no available models.",
                    details={"returnedModelCount": 0},
                ),
            ],
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

    async def list_cost_components(self, session, **kwargs):
        return []
