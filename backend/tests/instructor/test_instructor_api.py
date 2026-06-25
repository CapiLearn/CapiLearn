from datetime import date
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from backend.auth.dependencies import get_current_principal
from backend.auth.schemas import AuthPrincipal, UserRole
from backend.instructor.dependencies import get_instructor_dashboard_service
from backend.instructor.schemas import (
    InstructorDashboardResponse,
    InstructorStudentRosterRow,
)
from backend.main import app


@pytest.fixture(autouse=True)
def clear_overrides():
    app.openapi_schema = None
    yield
    app.dependency_overrides.clear()
    app.openapi_schema = None


def test_instructor_openapi_exposes_dashboard_route() -> None:
    schema = app.openapi()

    assert "/api/instructor/dashboard" in schema["paths"]
    assert (
        schema["paths"]["/api/instructor/dashboard"]["get"]["operationId"]
        == "getInstructorDashboard"
    )


def _authorize(role: UserRole = UserRole.INSTRUCTOR) -> None:
    app.dependency_overrides[get_current_principal] = lambda: AuthPrincipal(
        clerk_id=f"user_{role.value}_{uuid4().hex}",
        role=role,
    )


@pytest.mark.asyncio
async def test_instructor_dashboard_requires_bearer_auth() -> None:
    app.dependency_overrides[get_instructor_dashboard_service] = lambda: FakeInstructorService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/instructor/dashboard")

    assert response.status_code == 401
    assert response.json() == {
        "code": "auth_required",
        "message": "Authentication is required.",
        "details": None,
    }


@pytest.mark.asyncio
async def test_instructor_dashboard_accepts_instructor_role() -> None:
    _authorize(UserRole.INSTRUCTOR)
    service = FakeInstructorService()
    app.dependency_overrides[get_instructor_dashboard_service] = lambda: service

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/instructor/dashboard?fromDate=2026-05-01&toDate=2026-05-04"
        )

    assert response.status_code == 200
    assert response.json() == {
        "fromDate": "2026-05-01",
        "toDate": "2026-05-04",
        "activeStudents": 18,
        "questionsAsked": 142,
        "studentRoster": [
            {
                "displayName": "Student Demo",
                "messagesSent": 4,
                "messagesBlocked": 1,
            }
        ],
    }
    assert service.from_date == "2026-05-01"
    assert service.to_date == "2026-05-04"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [UserRole.STUDENT, UserRole.ADMIN])
async def test_instructor_dashboard_rejects_non_instructor_roles(role: UserRole) -> None:
    _authorize(role)
    app.dependency_overrides[get_instructor_dashboard_service] = lambda: FakeInstructorService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/instructor/dashboard")

    assert response.status_code == 403
    assert response.json() == {
        "code": "forbidden",
        "message": "This user does not have access to this resource.",
        "details": None,
    }


class FakeInstructorService:
    def __init__(self) -> None:
        self.from_date = None
        self.to_date = None

    async def get_dashboard(
        self,
        *,
        from_date: str | None,
        to_date: str | None,
    ) -> InstructorDashboardResponse:
        self.from_date = from_date
        self.to_date = to_date
        return InstructorDashboardResponse(
            from_date=date(2026, 5, 1),
            to_date=date(2026, 5, 4),
            active_students=18,
            questions_asked=142,
            student_roster=[
                InstructorStudentRosterRow(
                    display_name="Student Demo",
                    messages_sent=4,
                    messages_blocked=1,
                )
            ],
        )
