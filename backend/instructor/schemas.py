"""Pydantic schemas returned by instructor API endpoints."""

from datetime import date

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class InstructorBaseModel(BaseModel):
    """Base schema with camelCase aliases for instructor API payloads."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class InstructorStudentRosterRow(InstructorBaseModel):
    """Student activity row displayed in the instructor dashboard roster."""

    display_name: str
    messages_sent: int
    messages_blocked: int


class InstructorDashboardResponse(InstructorBaseModel):
    """Instructor dashboard response for a resolved reporting date range."""

    from_date: date
    to_date: date
    active_students: int
    questions_asked: int
    student_roster: list[InstructorStudentRosterRow]
