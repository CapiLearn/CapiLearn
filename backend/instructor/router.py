"""FastAPI routes for instructor-facing features."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from backend.instructor.dependencies import (
    InstructorDashboardServiceDep,
    require_instructor,
)
from backend.instructor.schemas import InstructorDashboardResponse

router = APIRouter(
    prefix="/instructor",
    tags=["instructor"],
    dependencies=[Depends(require_instructor)],
)


@router.get(
    "/dashboard",
    operation_id="getInstructorDashboard",
    summary="Get instructor dashboard",
)
async def get_instructor_dashboard(
    service: InstructorDashboardServiceDep,
    from_date: Annotated[str | None, Query(alias="fromDate")] = None,
    to_date: Annotated[str | None, Query(alias="toDate")] = None,
) -> InstructorDashboardResponse:
    """Fetch instructor dashboard metrics for an optional date range."""
    return await service.get_dashboard(from_date=from_date, to_date=to_date)
