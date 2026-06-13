from datetime import date

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ActivityBaseModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class LoginActivityResponse(ActivityBaseModel):
    activity_date: date
    current_streak: int
    logged_in_today: bool


class ActivityCalendarDay(ActivityBaseModel):
    date: date
    login_count: int


class ActivityCalendarResponse(ActivityBaseModel):
    current_streak: int
    days: list[ActivityCalendarDay]
