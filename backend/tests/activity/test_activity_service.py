from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from fastapi import status

from backend.activity.models import StudentDailyActivity
from backend.activity.service import StudentActivityService, eastern_activity_date
from backend.auth.schemas import CurrentUser, UserRole
from backend.core.exceptions import ApiError


def test_eastern_activity_date_uses_east_coast_midnight() -> None:
    assert eastern_activity_date(datetime(2026, 6, 14, 3, 59, 59, tzinfo=UTC)) == date(
        2026,
        6,
        13,
    )
    assert eastern_activity_date(datetime(2026, 6, 14, 4, 0, tzinfo=UTC)) == date(
        2026,
        6,
        14,
    )


@pytest.mark.asyncio
async def test_record_login_creates_activity_for_eastern_date() -> None:
    user = _current_user()
    repository = FakeActivityRepository()
    session = FakeSession()
    service = StudentActivityService(
        session=session,
        current_user=user,
        repository=repository,
        clock=lambda: datetime(2026, 6, 14, 3, 30, tzinfo=UTC),
    )

    response = await service.record_login()

    assert response.activity_date == date(2026, 6, 13)
    assert response.current_streak == 1
    assert response.logged_in_today is True
    assert session.commits == 1
    assert repository.records[date(2026, 6, 13)].login_count == 1


@pytest.mark.asyncio
async def test_record_login_updates_existing_eastern_day() -> None:
    user = _current_user()
    repository = FakeActivityRepository()
    session = FakeSession()
    clock = SequenceClock(
        datetime(2026, 6, 14, 3, 0, tzinfo=UTC),
        datetime(2026, 6, 14, 3, 30, tzinfo=UTC),
    )
    service = StudentActivityService(
        session=session,
        current_user=user,
        repository=repository,
        clock=clock,
    )

    first_response = await service.record_login()
    second_response = await service.record_login()

    assert first_response.activity_date == date(2026, 6, 13)
    assert second_response.activity_date == date(2026, 6, 13)
    assert repository.records[date(2026, 6, 13)].login_count == 2
    assert session.commits == 2


@pytest.mark.asyncio
async def test_current_streak_counts_from_yesterday_before_today_login() -> None:
    user = _current_user()
    repository = FakeActivityRepository(user_id=user.id)
    repository.seed(date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12))
    service = StudentActivityService(
        session=FakeSession(),
        current_user=user,
        repository=repository,
        clock=lambda: datetime(2026, 6, 13, 15, tzinfo=UTC),
    )

    response = await service.get_calendar(
        from_date=date(2026, 6, 1),
        to_date=date(2026, 6, 30),
    )

    assert response.current_streak == 3
    assert [day.date for day in response.days] == [
        date(2026, 6, 10),
        date(2026, 6, 11),
        date(2026, 6, 12),
    ]


@pytest.mark.asyncio
async def test_current_streak_stops_at_gap() -> None:
    user = _current_user()
    repository = FakeActivityRepository(user_id=user.id)
    repository.seed(date(2026, 6, 10), date(2026, 6, 12))
    service = StudentActivityService(
        session=FakeSession(),
        current_user=user,
        repository=repository,
        clock=lambda: datetime(2026, 6, 13, 15, tzinfo=UTC),
    )

    response = await service.get_calendar(
        from_date=date(2026, 6, 1),
        to_date=date(2026, 6, 30),
    )

    assert response.current_streak == 1


@pytest.mark.asyncio
async def test_calendar_rejects_invalid_date_range() -> None:
    service = StudentActivityService(
        session=FakeSession(),
        current_user=_current_user(),
        repository=FakeActivityRepository(),
    )

    with pytest.raises(ApiError) as exc_info:
        await service.get_calendar(
            from_date=date(2026, 6, 30),
            to_date=date(2026, 6, 1),
        )

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc_info.value.code == "invalid_date_range"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [UserRole.INSTRUCTOR, UserRole.ADMIN])
async def test_activity_requires_student_role(role: UserRole) -> None:
    service = StudentActivityService(
        session=FakeSession(),
        current_user=_current_user(role=role),
        repository=FakeActivityRepository(),
    )

    with pytest.raises(ApiError) as exc_info:
        await service.record_login()

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.code == "student_required"


def _current_user(role: UserRole = UserRole.STUDENT) -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        clerk_id=f"user_{role.value}_{uuid4().hex}",
        role=role,
    )


class SequenceClock:
    def __init__(self, *values: datetime) -> None:
        self._values = list(values)

    def __call__(self) -> datetime:
        return self._values.pop(0)


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class FakeActivityRepository:
    def __init__(self, user_id=None) -> None:
        self.user_id = user_id
        self.records: dict[date, StudentDailyActivity] = {}

    def seed(self, *activity_dates: date) -> None:
        user_id = self.user_id or uuid4()
        for activity_date in activity_dates:
            self.records[activity_date] = StudentDailyActivity(
                id=uuid4(),
                user_id=user_id,
                activity_date=activity_date,
                first_seen_at=datetime(2026, 6, 1, tzinfo=UTC),
                last_seen_at=datetime(2026, 6, 1, tzinfo=UTC),
                login_count=1,
            )

    async def record_login(self, session, *, user_id, activity_date, seen_at):
        if activity_date in self.records:
            activity = self.records[activity_date]
            activity.last_seen_at = seen_at
            activity.login_count += 1
            return activity

        activity = StudentDailyActivity(
            id=uuid4(),
            user_id=user_id,
            activity_date=activity_date,
            first_seen_at=seen_at,
            last_seen_at=seen_at,
            login_count=1,
        )
        self.records[activity_date] = activity
        return activity

    async def list_dates_through(self, session, *, user_id, through_date):
        return sorted(
            [activity_date for activity_date in self.records if activity_date <= through_date],
            reverse=True,
        )

    async def list_between(self, session, *, user_id, from_date, to_date):
        return [
            self.records[activity_date]
            for activity_date in sorted(self.records)
            if from_date <= activity_date <= to_date
        ]
