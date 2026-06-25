"""Pydantic schemas exposed by the student activity API."""

from datetime import date

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ActivityBaseModel(BaseModel):
    """Base schema using the API's camelCase response aliases."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class LoginActivityResponse(ActivityBaseModel):
    """Response returned after recording a login activity event."""

    activity_date: date
    current_streak: int
    logged_in_today: bool


class ActivityCalendarDay(ActivityBaseModel):
    """One day of login activity in a calendar response."""

    date: date
    login_count: int


class ActivityCalendarResponse(ActivityBaseModel):
    """Activity calendar data for a student and requested date range."""

    current_streak: int
    days: list[ActivityCalendarDay]
