from typing import Annotated

from fastapi import Depends

from backend.activity.service import StudentActivityService
from backend.auth.dependencies import CurrentUserDep
from backend.core.database import DbSession


def get_student_activity_service(
    session: DbSession,
    current_user: CurrentUserDep,
) -> StudentActivityService:
    return StudentActivityService(session=session, current_user=current_user)


StudentActivityServiceDep = Annotated[
    StudentActivityService,
    Depends(get_student_activity_service),
]
