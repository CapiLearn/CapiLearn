from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from backend.core.exceptions import ApiError
from backend.instructor.repository import InstructorSummaryAggregate
from backend.instructor.service import InstructorDashboardService
from backend.usage.repository import UserActivityAggregate

EASTERN_TIME = ZoneInfo("America/New_York")


@pytest.mark.asyncio
async def test_dashboard_maps_summary_and_roster_rows() -> None:
    repository = CapturingInstructorRepository(
        summary=InstructorSummaryAggregate(active_students=2, questions_asked=5),
        roster=[
            UserActivityAggregate(
                display_name="Maya Singh",
                access_level="student",
                total_messages_sent=3,
                blocked_requests=1,
                last_activity=datetime(2026, 5, 1, 10, tzinfo=UTC),
            )
        ],
    )
    service = InstructorDashboardService(
        session=object(),
        repository=repository,
        clock=lambda: datetime(2026, 5, 19, 12, tzinfo=UTC),
    )

    response = await service.get_dashboard(
        from_date="2026-05-01",
        to_date="2026-05-04",
    )

    assert repository.range_start == datetime(2026, 5, 1, tzinfo=EASTERN_TIME)
    assert repository.range_end == datetime(2026, 5, 4, tzinfo=EASTERN_TIME)
    assert repository.activity_from_date == date(2026, 5, 1)
    assert repository.activity_to_date == date(2026, 5, 4)
    assert repository.limit == 100
    assert response.model_dump(mode="json", by_alias=True) == {
        "fromDate": "2026-05-01",
        "toDate": "2026-05-04",
        "activeStudents": 2,
        "questionsAsked": 5,
        "studentRoster": [
            {
                "displayName": "Maya Singh",
                "messagesSent": 3,
                "messagesBlocked": 1,
            }
        ],
    }


@pytest.mark.asyncio
async def test_dashboard_defaults_to_last_seven_new_york_calendar_days() -> None:
    repository = CapturingInstructorRepository()
    service = InstructorDashboardService(
        session=object(),
        repository=repository,
        clock=lambda: datetime(2026, 5, 20, 2, tzinfo=UTC),
    )

    response = await service.get_dashboard(from_date=None, to_date=None)

    assert response.from_date == date(2026, 5, 13)
    assert response.to_date == date(2026, 5, 20)
    assert repository.range_start == datetime(2026, 5, 13, tzinfo=EASTERN_TIME)
    assert repository.range_end == datetime(2026, 5, 20, tzinfo=EASTERN_TIME)


@pytest.mark.asyncio
async def test_dashboard_rejects_non_iso_calendar_dates() -> None:
    repository = CapturingInstructorRepository()
    service = InstructorDashboardService(
        session=object(),
        repository=repository,
        clock=lambda: datetime(2026, 5, 19, 12, tzinfo=UTC),
    )

    with pytest.raises(ApiError) as exc_info:
        await service.get_dashboard(
            from_date="2026-5-01",
            to_date="2026-05-02",
        )

    assert exc_info.value.code == "invalid_date_range"
    assert exc_info.value.details == {
        "fromDate": "2026-5-01",
        "toDate": "2026-05-02",
    }
    assert repository.range_start is None
    assert repository.range_end is None


@pytest.mark.asyncio
async def test_dashboard_rejects_empty_ranges_before_querying() -> None:
    repository = CapturingInstructorRepository()
    service = InstructorDashboardService(
        session=object(),
        repository=repository,
        clock=lambda: datetime(2026, 5, 19, 12, tzinfo=UTC),
    )

    with pytest.raises(ApiError) as exc_info:
        await service.get_dashboard(
            from_date="2026-05-01",
            to_date="2026-05-01",
        )

    assert exc_info.value.code == "invalid_date_range"
    assert repository.range_start is None
    assert repository.range_end is None


@pytest.mark.asyncio
async def test_dashboard_rejects_ranges_over_366_days_before_querying() -> None:
    repository = CapturingInstructorRepository()
    service = InstructorDashboardService(
        session=object(),
        repository=repository,
        clock=lambda: datetime(2026, 5, 19, 12, tzinfo=UTC),
    )

    with pytest.raises(ApiError) as exc_info:
        await service.get_dashboard(
            from_date="2025-01-01",
            to_date="2026-01-03",
        )

    assert exc_info.value.code == "date_range_too_large"
    assert exc_info.value.details == {
        "fromDate": "2025-01-01",
        "toDate": "2026-01-03",
        "maxDays": 366,
    }
    assert repository.range_start is None
    assert repository.range_end is None


class CapturingInstructorRepository:
    def __init__(
        self,
        *,
        summary: InstructorSummaryAggregate | None = None,
        roster: list[UserActivityAggregate] | None = None,
    ) -> None:
        self.summary = summary or InstructorSummaryAggregate(
            active_students=0,
            questions_asked=0,
        )
        self.roster = roster or []
        self.range_start = None
        self.range_end = None
        self.activity_from_date = None
        self.activity_to_date = None
        self.limit = None

    async def get_summary_metrics(
        self,
        session,
        *,
        range_start,
        range_end,
        activity_from_date,
        activity_to_date,
    ):
        self.range_start = range_start
        self.range_end = range_end
        self.activity_from_date = activity_from_date
        self.activity_to_date = activity_to_date
        return self.summary

    async def list_student_roster(
        self,
        session,
        *,
        range_start,
        range_end,
        limit=100,
    ):
        self.range_start = range_start
        self.range_end = range_end
        self.limit = limit
        return self.roster
