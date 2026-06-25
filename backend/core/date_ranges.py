"""Shared date-window parsing for API filters."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo

from backend.core.exceptions import ApiError

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class DateWindow:
    """Resolved inclusive date labels and an exclusive datetime query window."""

    from_date: date
    to_date: date
    range_start: datetime
    range_end: datetime


def resolve_date_window(
    from_date: str | None,
    to_date: str | None,
    *,
    clock: Callable[[], datetime],
    timezone: tzinfo,
    max_days: int,
    invalid_message: str,
    too_large_message: str,
) -> DateWindow:
    """Resolve optional YYYY-MM-DD bounds into a timezone-aware query window."""
    resolved_to_date = (
        _parse_date(
            to_date,
            from_date=from_date,
            to_date=to_date,
            message=invalid_message,
        )
        if to_date is not None
        else clock().astimezone(timezone).date() + timedelta(days=1)
    )
    resolved_from_date = (
        _parse_date(
            from_date,
            from_date=from_date,
            to_date=to_date,
            message=invalid_message,
        )
        if from_date is not None
        else resolved_to_date - timedelta(days=7)
    )

    if resolved_to_date <= resolved_from_date:
        raise _invalid_date_range(
            from_date=from_date,
            to_date=to_date,
            message=invalid_message,
        )

    if (resolved_to_date - resolved_from_date).days > max_days:
        raise ApiError(
            code="date_range_too_large",
            message=too_large_message,
            details={
                "fromDate": from_date,
                "toDate": to_date,
                "maxDays": max_days,
            },
        )

    return DateWindow(
        from_date=resolved_from_date,
        to_date=resolved_to_date,
        # Use midnight-to-midnight bounds so to_date behaves as an exclusive
        # upper bound for timestamp queries.
        range_start=datetime.combine(resolved_from_date, time.min, tzinfo=timezone),
        range_end=datetime.combine(resolved_to_date, time.min, tzinfo=timezone),
    )


def _parse_date(
    value: str,
    *,
    from_date: str | None,
    to_date: str | None,
    message: str,
) -> date:
    if not DATE_PATTERN.fullmatch(value):
        raise _invalid_date_range(from_date=from_date, to_date=to_date, message=message)

    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise _invalid_date_range(from_date=from_date, to_date=to_date, message=message) from exc


def _invalid_date_range(*, from_date: str | None, to_date: str | None, message: str) -> ApiError:
    return ApiError(
        code="invalid_date_range",
        message=message,
        details={
            "fromDate": from_date,
            "toDate": to_date,
        },
    )
