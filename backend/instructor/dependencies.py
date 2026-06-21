from typing import Annotated

from fastapi import Depends

from backend.auth.dependencies import require_instructor as require_instructor
from backend.core.database import DbSession
from backend.instructor.service import InstructorDashboardService


def get_instructor_dashboard_service(session: DbSession) -> InstructorDashboardService:
    return InstructorDashboardService(session=session)


InstructorDashboardServiceDep = Annotated[
    InstructorDashboardService,
    Depends(get_instructor_dashboard_service),
]
