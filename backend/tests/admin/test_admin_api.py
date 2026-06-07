from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from backend.admin.dependencies import get_admin_usage_service
from backend.admin.repository import UsageMetricsAggregate
from backend.admin.schemas import (
    AdminUsageSummaryResponse,
    CostComponentResponse,
    CostComponentsResponse,
    UsageMetrics,
    UsageRange,
)
from backend.admin.service import AdminUsageService
from backend.auth.dependencies import (
    get_auth_request_verifier,
    get_existing_current_user,
    get_user_repository,
)
from backend.auth.models import UserAccount
from backend.auth.repository import UserAccountRepository
from backend.auth.schemas import ClerkAuthClaims, CurrentUser, UserRole
from backend.core.config import Settings, get_settings
from backend.core.database import get_db
from backend.main import app


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_admin_openapi_exposes_usage_summary_route() -> None:
    schema = app.openapi()

    assert "/api/admin/usage/summary" in schema["paths"]
    assert "/api/admin/usage/cost-components" in schema["paths"]
    assert (
        schema["paths"]["/api/admin/usage/summary"]["get"]["operationId"] == "getAdminUsageSummary"
    )
    assert (
        schema["paths"]["/api/admin/usage/cost-components"]["get"]["operationId"]
        == "listAdminUsageCostComponents"
    )


def _authorize(role: UserRole = UserRole.ADMIN) -> None:
    app.dependency_overrides[get_existing_current_user] = lambda: CurrentUser(
        id=uuid4(),
        clerk_id=f"user_{role.value}_{uuid4().hex}",
        role=role,
    )


@pytest.mark.asyncio
async def test_usage_summary_requires_bearer_auth() -> None:
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
        "code": "auth_required",
        "message": "Authentication is required.",
        "details": None,
    }
    assert missing_response.status_code == 401
    assert missing_response.json() == expected
    assert false_response.status_code == 401
    assert false_response.json() == expected


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
async def test_cost_components_endpoint_requires_auth() -> None:
    app.dependency_overrides[get_admin_usage_service] = lambda: FakeAdminUsageService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/admin/usage/cost-components")

    assert response.status_code == 401
    assert response.json()["code"] == "auth_required"


@pytest.mark.asyncio
async def test_cost_components_endpoint_returns_granular_rows() -> None:
    _authorize(UserRole.ADMIN)
    service = FakeAdminUsageService()
    app.dependency_overrides[get_admin_usage_service] = lambda: service

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/admin/usage/cost-components?fromDate=2026-05-01&toDate=2026-05-04"
            "&componentType=main_generation&limit=25&offset=50",
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
    _authorize(UserRole.ADMIN)
    app.dependency_overrides[get_admin_usage_service] = lambda: FakeAdminUsageService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/admin/usage/cost-components?limit=501",
        )

    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [UserRole.STUDENT, UserRole.INSTRUCTOR])
async def test_usage_summary_rejects_non_admin_roles(role: UserRole) -> None:
    _authorize(role)
    app.dependency_overrides[get_admin_usage_service] = lambda: FakeAdminUsageService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/admin/usage/summary")

    assert response.status_code == 403
    assert response.json() == {
        "code": "admin_required",
        "message": "Admin access is required.",
        "details": None,
    }


@pytest.mark.asyncio
async def test_usage_summary_rejects_missing_local_user_without_provisioning() -> None:
    repository = FakeUserRepository()
    app.dependency_overrides[get_db] = _fake_db_override(FakeSession())
    app.dependency_overrides[get_user_repository] = lambda: repository
    app.dependency_overrides[get_auth_request_verifier] = lambda: FakeVerifier(
        ClerkAuthClaims(clerk_id="user_missing", claims={"sub": "user_missing"})
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
    assert repository.calls == [("get_by_clerk_id", "user_missing")]
    assert repository.user is None


@pytest.mark.asyncio
async def test_usage_summary_rejects_existing_non_admin_local_user() -> None:
    user = UserAccount(
        id=uuid4(),
        clerk_id="user_student",
        role=UserRole.STUDENT.value,
    )
    repository = FakeUserRepository(user=user)
    app.dependency_overrides[get_db] = _fake_db_override(FakeSession())
    app.dependency_overrides[get_user_repository] = lambda: repository
    app.dependency_overrides[get_auth_request_verifier] = lambda: FakeVerifier(
        ClerkAuthClaims(clerk_id="user_student", claims={"sub": "user_student"})
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
    assert repository.calls == [("get_by_clerk_id", "user_student")]


@pytest.mark.asyncio
async def test_usage_summary_rejects_existing_disabled_admin_local_user() -> None:
    user = UserAccount(
        id=uuid4(),
        clerk_id="user_disabled_admin",
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
        "code": "admin_required",
        "message": "Admin access is required.",
        "details": None,
    }
    assert repository.calls == [("get_by_clerk_id", "user_disabled_admin")]
    assert session.commits == 0


@pytest.mark.asyncio
async def test_usage_summary_accepts_existing_admin_local_user() -> None:
    user = UserAccount(
        id=uuid4(),
        clerk_id="user_admin",
        role=UserRole.ADMIN.value,
    )
    repository = FakeUserRepository(user=user)
    app.dependency_overrides[get_db] = _fake_db_override(FakeSession())
    app.dependency_overrides[get_user_repository] = lambda: repository
    app.dependency_overrides[get_auth_request_verifier] = lambda: FakeVerifier(
        ClerkAuthClaims(clerk_id="user_admin", claims={"sub": "user_admin"})
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
    assert repository.calls == [("get_by_clerk_id", "user_admin")]


@pytest.mark.asyncio
async def test_test_auth_mode_rejects_non_admin_role() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        auth_mode="test",
        test_auth_clerk_id="user_test_student",
        test_auth_role="student",
    )
    app.dependency_overrides[get_db] = _fake_db_override(FakeSession())
    app.dependency_overrides[get_user_repository] = lambda: FakeUserRepository()
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


@pytest.mark.asyncio
async def test_test_auth_mode_accepts_admin_role() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        auth_mode="test",
        test_auth_clerk_id="user_test_admin",
        test_auth_role="admin",
    )
    app.dependency_overrides[get_db] = _fake_db_override(FakeSession())
    app.dependency_overrides[get_user_repository] = lambda: FakeUserRepository()
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


@pytest.mark.asyncio
async def test_test_auth_mode_rejects_disabled_local_user_before_admin_role_gate() -> None:
    user = UserAccount(
        id=uuid4(),
        clerk_id="user_test_disabled",
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
        "code": "admin_required",
        "message": "Admin access is required.",
        "details": None,
    }
    assert repository.calls == [("get_by_clerk_id", "user_test_disabled")]
    assert session.commits == 0


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


class FakeUserRepository(UserAccountRepository):
    def __init__(self, user: UserAccount | None = None) -> None:
        self.user = user
        self.calls = []

    async def get_by_clerk_id(self, session, *, clerk_id: str) -> UserAccount | None:
        self.calls.append(("get_by_clerk_id", clerk_id))
        return self.user

    async def create(
        self,
        session,
        *,
        clerk_id: str,
        role: UserRole = UserRole.STUDENT,
    ) -> UserAccount:
        self.calls.append(("create", clerk_id, role))
        self.user = UserAccount(
            id=uuid4(),
            clerk_id=clerk_id,
            role=role.value,
        )
        return self.user
