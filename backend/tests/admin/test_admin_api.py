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
    AdminUserOverview,
    AdminUserOverviewResponse,
    CostComponentResponse,
    CostComponentsResponse,
    HealthStatus,
    UsageMetrics,
    UsageRange,
)
from backend.admin.service import AdminUsageService
from backend.auth.dependencies import (
    get_auth_request_verifier,
    get_current_principal,
    get_user_repository,
)
from backend.auth.models import UserAccount
from backend.auth.schemas import (
    AuthPrincipal,
    ClerkAuthClaims,
    UserRole,
)
from backend.core.config import Settings, get_settings
from backend.core.database import get_db
from backend.main import app
from backend.tests.fakes import FakeUserRepository


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_admin_openapi_exposes_usage_summary_route() -> None:
    schema = app.openapi()

    assert "/api/admin/health" in schema["paths"]
    assert "/api/admin/usage/summary" in schema["paths"]
    assert "/api/admin/users/overview" in schema["paths"]
    assert "/api/admin/usage/cost-components" in schema["paths"]
    assert schema["paths"]["/api/admin/health"]["get"]["operationId"] == "getAdminHealth"
    assert (
        schema["paths"]["/api/admin/usage/summary"]["get"]["operationId"] == "getAdminUsageSummary"
    )
    assert (
        schema["paths"]["/api/admin/users/overview"]["get"]["operationId"]
        == "listAdminUserOverviews"
    )
    assert (
        schema["paths"]["/api/admin/usage/cost-components"]["get"]["operationId"]
        == "listAdminUsageCostComponents"
    )


def _authorize(role: UserRole = UserRole.ADMIN) -> None:
    app.dependency_overrides[get_current_principal] = lambda: AuthPrincipal(
        clerk_id=f"user_{role.value}_{uuid4().hex}",
        role=role,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "service_dependency"),
    [
        ("/api/admin/usage/summary", get_admin_usage_service),
        ("/api/admin/usage/cost-components", get_admin_usage_service),
        ("/api/admin/users/overview", get_admin_usage_service),
        ("/api/admin/health", get_admin_health_service),
    ],
)
async def test_admin_endpoints_require_bearer_auth(path, service_dependency) -> None:
    service = (
        FakeAdminHealthService()
        if service_dependency is get_admin_health_service
        else FakeAdminUsageService()
    )
    app.dependency_overrides[service_dependency] = lambda: service

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(path)

    expected = {
        "code": "auth_required",
        "message": "Authentication is required.",
        "details": None,
    }
    assert response.status_code == 401
    assert response.json() == expected


@pytest.mark.asyncio
async def test_usage_summary_ignores_old_admin_header() -> None:
    app.dependency_overrides[get_admin_usage_service] = lambda: FakeAdminUsageService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/admin/usage/summary",
            headers={"X-Admin-User": " TRUE "},
        )

    assert response.status_code == 401
    assert response.json()["code"] == "auth_required"


@pytest.mark.asyncio
async def test_usage_summary_accepts_admin_role() -> None:
    _authorize(UserRole.ADMIN)
    app.dependency_overrides[get_admin_usage_service] = lambda: FakeAdminUsageService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/admin/usage/summary")

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
    _authorize(UserRole.ADMIN)
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
    _authorize(UserRole.ADMIN)
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
async def test_cost_components_endpoint_returns_granular_rows() -> None:
    _authorize(UserRole.ADMIN)
    service = FakeAdminUsageService()
    conversation_id = uuid4()
    assistant_message_id = uuid4()
    app.dependency_overrides[get_admin_usage_service] = lambda: service

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/admin/usage/cost-components?fromDate=2026-05-01&toDate=2026-05-04"
            f"&conversationId={conversation_id}&assistantMessageId={assistant_message_id}"
            "&componentType=repair_generation&limit=25&offset=50",
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["range"] == {
        "fromDate": "2026-05-01",
        "toDate": "2026-05-04",
    }
    assert payload["costComponents"][0]["componentType"] == "repair_generation"
    assert payload["costComponents"][0]["estimatedCostUsd"] == "0.001000000000"
    assert service.from_date == "2026-05-01"
    assert service.to_date == "2026-05-04"
    assert service.conversation_id == conversation_id
    assert service.assistant_message_id == assistant_message_id
    assert service.component_type == "repair_generation"
    assert service.limit == 25
    assert service.offset == 50


@pytest.mark.asyncio
async def test_user_overviews_endpoint_returns_camel_case_rows_and_forwards_params() -> None:
    _authorize(UserRole.ADMIN)
    service = FakeAdminUsageService()
    app.dependency_overrides[get_admin_usage_service] = lambda: service

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/admin/users/overview?fromDate=2026-05-01&toDate=2026-05-04&limit=25&offset=50",
        )

    assert response.status_code == 200
    assert response.json()["users"][0]["displayName"] == "Student Demo"
    assert service.from_date == "2026-05-01"
    assert service.to_date == "2026-05-04"
    assert service.limit == 25
    assert service.offset == 50


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "query"),
    [
        ("/api/admin/usage/cost-components", "limit=501"),
        ("/api/admin/usage/cost-components", "offset=-1"),
        ("/api/admin/users/overview", "limit=501"),
        ("/api/admin/users/overview", "offset=-1"),
    ],
)
async def test_admin_paginated_endpoints_reject_invalid_pagination(
    path: str,
    query: str,
) -> None:
    _authorize(UserRole.ADMIN)
    app.dependency_overrides[get_admin_usage_service] = lambda: FakeAdminUsageService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(f"{path}?{query}")

    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/api/admin/usage/summary",
        "/api/admin/users/overview",
    ],
)
@pytest.mark.parametrize("role", [UserRole.STUDENT, UserRole.INSTRUCTOR])
async def test_admin_usage_endpoints_reject_non_admin_roles(
    path: str,
    role: UserRole,
) -> None:
    _authorize(role)
    app.dependency_overrides[get_admin_usage_service] = lambda: FakeAdminUsageService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(path)

    assert response.status_code == 403
    assert response.json() == {
        "code": "admin_required",
        "message": "Admin access is required.",
        "details": None,
    }


@pytest.mark.asyncio
async def test_usage_summary_rejects_missing_local_user_without_provisioning() -> None:
    repository = FakeUserRepository()
    session = FakeSession()
    app.dependency_overrides[get_settings] = lambda: Settings(auth_mode="clerk")
    app.dependency_overrides[get_db] = _fake_db_override(session)
    app.dependency_overrides[get_user_repository] = lambda: repository
    app.dependency_overrides[get_auth_request_verifier] = lambda: FakeVerifier(
        ClerkAuthClaims(
            clerk_id="user_missing",
            display_name="Missing User",
            claims={"sub": "user_missing"},
        )
    )
    app.dependency_overrides[get_admin_usage_service] = lambda: FakeAdminUsageService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/admin/usage/summary",
            headers={"Authorization": "Bearer clerk"},
        )

    assert response.status_code == 403
    assert response.json() == {
        "code": "admin_required",
        "message": "Admin access is required.",
        "details": None,
    }
    assert repository.user is None
    assert session.commits == 0


@pytest.mark.asyncio
async def test_usage_summary_rejects_existing_non_admin_local_user() -> None:
    user = UserAccount(
        id=uuid4(),
        clerk_id="user_student",
        display_name="Student User",
        email="student@example.com",
        profile_synced_at=datetime(2026, 6, 1, tzinfo=UTC),
        role=UserRole.STUDENT.value,
    )
    original_synced_at = user.profile_synced_at
    repository = FakeUserRepository(user=user)
    session = FakeSession()
    app.dependency_overrides[get_db] = _fake_db_override(session)
    app.dependency_overrides[get_user_repository] = lambda: repository
    app.dependency_overrides[get_auth_request_verifier] = lambda: FakeVerifier(
        ClerkAuthClaims(
            clerk_id="user_student",
            email="changed@example.com",
            display_name="Changed Student",
            claims={"sub": "user_student"},
        )
    )
    app.dependency_overrides[get_admin_usage_service] = lambda: FakeAdminUsageService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/admin/usage/summary",
            headers={"Authorization": "Bearer clerk"},
        )

    assert response.status_code == 403
    assert response.json()["code"] == "admin_required"
    assert repository.profile_update_calls == []
    assert user.email == "student@example.com"
    assert user.display_name == "Student User"
    assert user.profile_synced_at == original_synced_at
    assert session.commits == 0


@pytest.mark.asyncio
async def test_usage_summary_rejects_existing_disabled_admin_local_user() -> None:
    user = UserAccount(
        id=uuid4(),
        clerk_id="user_disabled_admin",
        display_name="Disabled Admin",
        profile_synced_at=datetime(2026, 6, 1, tzinfo=UTC),
        role=UserRole.ADMIN.value,
        deleted_at=datetime.now(UTC),
    )
    repository = FakeUserRepository(user=user)
    session = FakeSession()
    app.dependency_overrides[get_db] = _fake_db_override(session)
    app.dependency_overrides[get_user_repository] = lambda: repository
    app.dependency_overrides[get_auth_request_verifier] = lambda: FakeVerifier(
        ClerkAuthClaims(
            clerk_id="user_disabled_admin",
            display_name="Disabled Admin",
            claims={"sub": "user_disabled_admin"},
        )
    )
    app.dependency_overrides[get_admin_usage_service] = lambda: FakeAdminUsageService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/admin/usage/summary",
            headers={"Authorization": "Bearer clerk"},
        )

    assert response.status_code == 403
    assert response.json() == {
        "code": "forbidden",
        "message": "This user account is disabled.",
        "details": None,
    }
    assert session.commits == 0


@pytest.mark.asyncio
async def test_usage_summary_accepts_existing_admin_local_user() -> None:
    user = UserAccount(
        id=uuid4(),
        clerk_id="user_admin",
        display_name="Admin User",
        profile_synced_at=datetime(2026, 6, 1, tzinfo=UTC),
        role=UserRole.ADMIN.value,
    )
    original_synced_at = user.profile_synced_at
    repository = FakeUserRepository(user=user)
    session = FakeSession()
    app.dependency_overrides[get_settings] = lambda: Settings(auth_mode="clerk")
    app.dependency_overrides[get_db] = _fake_db_override(session)
    app.dependency_overrides[get_user_repository] = lambda: repository
    app.dependency_overrides[get_auth_request_verifier] = lambda: FakeVerifier(
        ClerkAuthClaims(
            clerk_id="user_admin",
            display_name="Admin User",
            claims={"sub": "user_admin"},
        )
    )
    app.dependency_overrides[get_admin_usage_service] = lambda: FakeAdminUsageService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/admin/usage/summary",
            headers={"Authorization": "Bearer clerk"},
        )

    assert response.status_code == 200
    assert response.json()["metrics"]["totalUsers"] == 18
    assert user.profile_synced_at == original_synced_at
    assert session.commits == 0


@pytest.mark.asyncio
async def test_test_auth_mode_rejects_non_admin_role() -> None:
    repository = FakeUserRepository()
    session = FakeSession()
    app.dependency_overrides[get_settings] = lambda: Settings(
        auth_mode="test",
        test_auth_clerk_id="user_test_student",
        test_auth_role="student",
    )
    app.dependency_overrides[get_db] = _fake_db_override(session)
    app.dependency_overrides[get_user_repository] = lambda: repository
    app.dependency_overrides[get_admin_usage_service] = lambda: FakeAdminUsageService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/admin/usage/summary",
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 403
    assert response.json()["code"] == "admin_required"
    assert repository.user is None
    assert session.commits == 0


@pytest.mark.asyncio
async def test_test_auth_mode_accepts_admin_role() -> None:
    user = UserAccount(
        id=uuid4(),
        clerk_id="user_test_admin",
        display_name="Test Admin",
        profile_synced_at=datetime(2026, 6, 1, tzinfo=UTC),
        role=UserRole.STUDENT.value,
    )
    repository = FakeUserRepository(user=user)
    session = FakeSession()
    app.dependency_overrides[get_settings] = lambda: Settings(
        auth_mode="test",
        test_auth_clerk_id="user_test_admin",
        test_auth_role="admin",
    )
    app.dependency_overrides[get_db] = _fake_db_override(session)
    app.dependency_overrides[get_user_repository] = lambda: repository
    app.dependency_overrides[get_admin_usage_service] = lambda: FakeAdminUsageService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/admin/usage/summary",
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 200
    assert response.json()["metrics"]["totalUsers"] == 18
    assert repository.user is user
    assert session.commits == 0


@pytest.mark.asyncio
async def test_test_auth_mode_rejects_disabled_local_user_before_admin_role_gate() -> None:
    user = UserAccount(
        id=uuid4(),
        clerk_id="user_test_disabled",
        display_name="Disabled User",
        profile_synced_at=datetime(2026, 6, 1, tzinfo=UTC),
        role=UserRole.STUDENT.value,
        deleted_at=datetime.now(UTC),
    )
    repository = FakeUserRepository(user=user)
    session = FakeSession()
    app.dependency_overrides[get_settings] = lambda: Settings(
        auth_mode="test",
        test_auth_clerk_id="user_test_disabled",
        test_auth_role="admin",
    )
    app.dependency_overrides[get_db] = _fake_db_override(session)
    app.dependency_overrides[get_user_repository] = lambda: repository
    app.dependency_overrides[get_admin_usage_service] = lambda: FakeAdminUsageService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/admin/usage/summary",
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 403
    assert response.json() == {
        "code": "forbidden",
        "message": "This user account is disabled.",
        "details": None,
    }
    assert session.commits == 0


@pytest.mark.asyncio
async def test_admin_health_returns_camel_case_response() -> None:
    _authorize(UserRole.ADMIN)
    app.dependency_overrides[get_admin_health_service] = lambda: FakeAdminHealthService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/admin/health")

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
                "name": "llmProviderMetadata",
                "status": "degraded",
                "latencyMs": None,
                "message": "Provider metadata returned no available models.",
                "details": {"returnedModelCount": 0},
            },
        ],
    }


class FakeAdminUsageService:
    def __init__(self) -> None:
        self.from_date = None
        self.to_date = None
        self.conversation_id = None
        self.assistant_message_id = None
        self.component_type = None
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
        self.from_date = from_date
        self.to_date = to_date
        self.conversation_id = conversation_id
        self.assistant_message_id = assistant_message_id
        self.component_type = component_type
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

    async def list_user_overviews(
        self,
        *,
        from_date: str | None,
        to_date: str | None,
        limit: int = 100,
        offset: int = 0,
    ) -> AdminUserOverviewResponse:
        self.from_date = from_date
        self.to_date = to_date
        self.limit = limit
        self.offset = offset
        return AdminUserOverviewResponse(
            range=UsageRange(from_date="2026-05-01", to_date="2026-05-04"),
            users=[
                AdminUserOverview(
                    id="00000000-0000-0000-0000-000000000123",
                    clerk_id="user_clerk_123",
                    display_name="Student Demo",
                    email="student@example.com",
                    access_level=UserRole.STUDENT,
                    total_messages=4,
                    blocked_requests=1,
                    last_activity=datetime(2026, 5, 2, 16, 30, tzinfo=UTC),
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
                    name="llmProviderMetadata",
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

    async def list_user_overviews(
        self,
        session,
        *,
        range_start,
        range_end,
        limit=100,
        offset=0,
    ):
        return []


class FakeVerifier:
    def __init__(self, claims: ClerkAuthClaims) -> None:
        self._claims = claims

    async def verify(self, bearer_token: str):
        return self._claims


def _fake_db_override(session):
    async def override():
        yield session

    return override


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1
