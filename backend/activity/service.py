from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.activity.repository import StudentDailyActivityRepository
from backend.activity.schemas import (
    ActivityCalendarDay,
    ActivityCalendarResponse,
    LoginActivityResponse,
)
from backend.auth.schemas import CurrentUser
from backend.core.exceptions import ApiError

EASTERN_TIME = ZoneInfo("America/New_York")


class StudentActivityService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        current_user: CurrentUser,
        repository: StudentDailyActivityRepository | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session = session
        self._current_user = current_user
        self._repository = repository or StudentDailyActivityRepository()
        self._clock = clock or _utc_now

    async def record_login(self) -> LoginActivityResponse:
        seen_at = _as_utc(self._clock())
        activity_date = eastern_activity_date(seen_at)
        await self._repository.record_login(
            self._session,
            user_id=self._current_user.id,
            activity_date=activity_date,
            seen_at=seen_at,
        )
        current_streak = await self._current_streak(current_date=activity_date)
        await self._session.commit()
        return LoginActivityResponse(
            activity_date=activity_date,
            current_streak=current_streak,
            logged_in_today=True,
        )

    async def get_calendar(
        self,
        *,
        from_date: date,
        to_date: date,
    ) -> ActivityCalendarResponse:
        if from_date > to_date:
            raise ApiError(
                code="invalid_date_range",
                message="Activity calendar ranges must have fromDate on or before toDate.",
                status_code=status.HTTP_400_BAD_REQUEST,
                details={
                    "fromDate": from_date.isoformat(),
                    "toDate": to_date.isoformat(),
                },
            )

        days = await self._repository.list_between(
            self._session,
            user_id=self._current_user.id,
            from_date=from_date,
            to_date=to_date,
        )
        current_streak = await self._current_streak(
            current_date=eastern_activity_date(_as_utc(self._clock())),
        )
        return ActivityCalendarResponse(
            current_streak=current_streak,
            days=[
                ActivityCalendarDay(
                    date=activity.activity_date,
                    login_count=activity.login_count,
                )
                for activity in days
            ],
        )

    async def _current_streak(self, *, current_date: date) -> int:
        dates = await self._repository.list_dates_through(
            self._session,
            user_id=self._current_user.id,
            through_date=current_date,
        )
        return current_streak(dates, current_date=current_date)


def eastern_activity_date(value: datetime) -> date:
    return _as_utc(value).astimezone(EASTERN_TIME).date()


def current_streak(activity_dates: Sequence[date], *, current_date: date) -> int:
    activity_date_set = set(activity_dates)
    streak_date = (
        current_date if current_date in activity_date_set else current_date - timedelta(days=1)
    )
    streak = 0
    while streak_date in activity_date_set:
        streak += 1
        streak_date -= timedelta(days=1)
    return streak


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Activity timestamps must be timezone-aware.")
    return value.astimezone(UTC)


def _utc_now() -> datetime:
    return datetime.now(UTC)
