"""Application service for instructor dashboard workflows."""

from collections.abc import Callable
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.date_ranges import DateWindow, resolve_date_window
from backend.instructor.repository import InstructorDashboardRepository
from backend.instructor.schemas import (
    InstructorDashboardResponse,
    InstructorStudentRosterRow,
)

EASTERN_TIME = ZoneInfo("America/New_York")
DATE_RANGE_ERROR = (
    "Instructor dashboard ranges must use America/New_York calendar dates "
    "and span at least one day."
)
MAX_INSTRUCTOR_DASHBOARD_RANGE_DAYS = 366
DEFAULT_ROSTER_LIMIT = 100


class InstructorDashboardService:
    """Coordinate instructor dashboard reads and response shaping."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        repository: InstructorDashboardRepository | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Create a service with injectable persistence and time dependencies."""
        self._session = session
        self._repository = repository or InstructorDashboardRepository()
        self._clock = clock or (lambda: datetime.now(UTC))

    async def get_dashboard(
        self,
        *,
        from_date: str | None,
        to_date: str | None,
    ) -> InstructorDashboardResponse:
        """Return dashboard metrics and roster activity for the requested range."""
        window = self._resolve_window(from_date=from_date, to_date=to_date)
        summary = await self._repository.get_summary_metrics(
            self._session,
            range_start=window.range_start,
            range_end=window.range_end,
            activity_from_date=window.from_date,
            activity_to_date=window.to_date,
        )
        roster = await self._repository.list_student_roster(
            self._session,
            range_start=window.range_start,
            range_end=window.range_end,
            limit=DEFAULT_ROSTER_LIMIT,
        )

        return InstructorDashboardResponse(
            from_date=window.from_date,
            to_date=window.to_date,
            active_students=summary.active_students,
            questions_asked=summary.questions_asked,
            student_roster=[
                InstructorStudentRosterRow(
                    display_name=student.display_name,
                    messages_sent=student.total_messages_sent,
                    messages_blocked=student.blocked_requests,
                )
                for student in roster
            ],
        )

    def _resolve_window(
        self,
        *,
        from_date: str | None,
        to_date: str | None,
    ) -> DateWindow:
        """Resolve API date strings using the instructor dashboard range rules."""
        return resolve_date_window(
            from_date,
            to_date,
            clock=self._clock,
            timezone=EASTERN_TIME,
            max_days=MAX_INSTRUCTOR_DASHBOARD_RANGE_DAYS,
            invalid_message=DATE_RANGE_ERROR,
            too_large_message=(
                "Instructor dashboard ranges cannot exceed "
                f"{MAX_INSTRUCTOR_DASHBOARD_RANGE_DAYS} days."
            ),
        )
