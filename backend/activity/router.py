"""FastAPI routes for student activity tracking."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from backend.activity.dependencies import StudentActivityServiceDep
from backend.activity.schemas import ActivityCalendarResponse, LoginActivityResponse

router = APIRouter(
    prefix="/activity",
    tags=["activity"],
)


@router.post(
    "/login",
    operation_id="recordLoginActivity",
    summary="Record daily login activity",
)
async def record_login_activity(
    service: StudentActivityServiceDep,
) -> LoginActivityResponse:
    """Record the authenticated student's login for the current activity day."""
    return await service.record_login()


@router.get(
    "/calendar",
    operation_id="getActivityCalendar",
    summary="Get activity calendar",
)
async def get_activity_calendar(
    service: StudentActivityServiceDep,
    from_date: Annotated[date, Query(alias="fromDate")],
    to_date: Annotated[date, Query(alias="toDate")],
) -> ActivityCalendarResponse:
    """Return login activity for the inclusive requested activity-date range."""
    return await service.get_calendar(from_date=from_date, to_date=to_date)
