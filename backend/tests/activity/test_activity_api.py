from datetime import date
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from backend.activity.dependencies import get_student_activity_service
from backend.activity.schemas import ActivityCalendarResponse, LoginActivityResponse
from backend.auth.dependencies import get_current_user
from backend.auth.schemas import CurrentUser, UserRole
from backend.main import app


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_login_activity_requires_auth() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/activity/login")

    assert response.status_code == 401
    assert response.json()["code"] == "auth_required"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [UserRole.INSTRUCTOR, UserRole.ADMIN])
async def test_login_activity_rejects_non_student_roles(role: UserRole) -> None:
    app.dependency_overrides[get_current_user] = lambda: _current_user(role=role)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/activity/login")

    assert response.status_code == 403
    assert response.json() == {
        "code": "student_required",
        "message": "Student access is required.",
        "details": None,
    }


@pytest.mark.asyncio
async def test_login_activity_returns_frontend_contract() -> None:
    app.dependency_overrides[get_student_activity_service] = lambda: FakeActivityService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/activity/login")

    assert response.status_code == 200
    assert response.json() == {
        "activityDate": "2026-06-13",
        "currentStreak": 5,
        "loggedInToday": True,
    }


@pytest.mark.asyncio
async def test_activity_calendar_returns_frontend_contract() -> None:
    app.dependency_overrides[get_student_activity_service] = lambda: FakeActivityService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/activity/calendar?fromDate=2026-06-01&toDate=2026-06-30",
        )

    assert response.status_code == 200
    assert response.json() == {
        "currentStreak": 5,
        "days": [
            {
                "date": "2026-06-12",
                "loginCount": 1,
            },
            {
                "date": "2026-06-13",
                "loginCount": 2,
            },
        ],
    }


def _current_user(role: UserRole = UserRole.STUDENT) -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        clerk_id=f"user_{role.value}_{uuid4().hex}",
        display_name="Test User",
        role=role,
    )


class FakeActivityService:
    async def record_login(self) -> LoginActivityResponse:
        return LoginActivityResponse(
            activity_date=date(2026, 6, 13),
            current_streak=5,
            logged_in_today=True,
        )

    async def get_calendar(self, *, from_date: date, to_date: date) -> ActivityCalendarResponse:
        assert from_date == date(2026, 6, 1)
        assert to_date == date(2026, 6, 30)
        return ActivityCalendarResponse(
            current_streak=5,
            days=[
                {
                    "date": date(2026, 6, 12),
                    "login_count": 1,
                },
                {
                    "date": date(2026, 6, 13),
                    "login_count": 2,
                },
            ],
        )
