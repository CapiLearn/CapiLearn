from datetime import date

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class InstructorBaseModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class InstructorStudentRosterRow(InstructorBaseModel):
    display_name: str
    messages_sent: int
    messages_blocked: int


class InstructorDashboardResponse(InstructorBaseModel):
    from_date: date
    to_date: date
    active_students: int
    questions_asked: int
    student_roster: list[InstructorStudentRosterRow]
