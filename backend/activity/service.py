"""Business logic for student login activity and streak calculations."""

from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.activity.dates import as_utc as _as_utc
from backend.activity.dates import eastern_activity_date
from backend.activity.repository import StudentDailyActivityRepository
from backend.activity.schemas import (
    ActivityCalendarDay,
    ActivityCalendarResponse,
    LoginActivityResponse,
)
from backend.core.exceptions import ApiError


class StudentActivityService:
    """Coordinates activity persistence and response shaping for the current student."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        user_id: UUID,
        repository: StudentDailyActivityRepository | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session = session
        self._user_id = user_id
        self._repository = repository or StudentDailyActivityRepository()
        self._clock = clock or _utc_now

    async def record_login(self) -> LoginActivityResponse:
        """Persist a login and return the student's updated activity state."""
        seen_at = _as_utc(self._clock())
        # Activity follows the school-day boundary used by the product, not UTC midnights.
        activity_date = eastern_activity_date(seen_at)
        await self._repository.record_login(
            self._session,
            user_id=self._user_id,
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
        """Return activity rows and the current streak for a date range."""
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
            user_id=self._user_id,
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
        """Load activity dates needed to calculate the streak visible today."""
        dates = await self._repository.list_dates_through(
            self._session,
            user_id=self._user_id,
            through_date=current_date,
        )
        return current_streak(dates, current_date=current_date)


def current_streak(activity_dates: Sequence[date], *, current_date: date) -> int:
    """Return consecutive activity days ending today, or yesterday if today is inactive."""
    activity_date_set = set(activity_dates)
    streak_date = (
        current_date if current_date in activity_date_set else current_date - timedelta(days=1)
    )
    streak = 0
    while streak_date in activity_date_set:
        streak += 1
        streak_date -= timedelta(days=1)
    return streak


def _utc_now() -> datetime:
    return datetime.now(UTC)
