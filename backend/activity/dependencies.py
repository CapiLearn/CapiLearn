from typing import Annotated

from fastapi import Depends

from backend.activity.service import StudentActivityService
from backend.auth.dependencies import StudentUserDep
from backend.core.database import DbSession


def get_student_activity_service(
    session: DbSession,
    current_user: StudentUserDep,
) -> StudentActivityService:
    return StudentActivityService(session=session, current_user=current_user)


StudentActivityServiceDep = Annotated[
    StudentActivityService,
    Depends(get_student_activity_service),
]
