from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from backend.core.date_ranges import resolve_date_window
from backend.core.exceptions import ApiError

PACIFIC_TIME = ZoneInfo("America/Los_Angeles")


def test_resolve_date_window_uses_requested_timezone_for_explicit_range() -> None:
    window = resolve_date_window(
        "2026-05-01",
        "2026-05-03",
        clock=lambda: datetime(2026, 5, 19, 12, tzinfo=UTC),
        timezone=PACIFIC_TIME,
        max_days=366,
        invalid_message="Invalid range.",
        too_large_message="Range too large.",
    )

    assert window.from_date == date(2026, 5, 1)
    assert window.to_date == date(2026, 5, 3)
    assert window.range_start == datetime(2026, 5, 1, tzinfo=PACIFIC_TIME)
    assert window.range_end == datetime(2026, 5, 3, tzinfo=PACIFIC_TIME)
    assert window.range_end - window.range_start == timedelta(days=2)


def test_resolve_date_window_defaults_from_requested_timezone_current_date() -> None:
    window = resolve_date_window(
        None,
        None,
        clock=lambda: datetime(2026, 5, 20, 2, tzinfo=UTC),
        timezone=PACIFIC_TIME,
        max_days=366,
        invalid_message="Invalid range.",
        too_large_message="Range too large.",
    )

    assert window.from_date == date(2026, 5, 13)
    assert window.to_date == date(2026, 5, 20)
    assert window.range_start == datetime(2026, 5, 13, tzinfo=PACIFIC_TIME)
    assert window.range_end == datetime(2026, 5, 20, tzinfo=PACIFIC_TIME)


@pytest.mark.parametrize(
    ("from_date", "to_date"),
    [
        ("2026-5-01", "2026-05-02"),
        ("2026-05-01", "2026-05-01"),
    ],
)
def test_resolve_date_window_rejects_invalid_ranges(
    from_date: str,
    to_date: str,
) -> None:
    with pytest.raises(ApiError) as exc_info:
        resolve_date_window(
            from_date,
            to_date,
            clock=lambda: datetime(2026, 5, 19, 12, tzinfo=UTC),
            timezone=UTC,
            max_days=366,
            invalid_message="Invalid range.",
            too_large_message="Range too large.",
        )

    assert exc_info.value.code == "invalid_date_range"
    assert exc_info.value.message == "Invalid range."
    assert exc_info.value.details == {
        "fromDate": from_date,
        "toDate": to_date,
    }


def test_resolve_date_window_rejects_ranges_over_max_days() -> None:
    with pytest.raises(ApiError) as exc_info:
        resolve_date_window(
            "2025-01-01",
            "2026-01-03",
            clock=lambda: datetime(2026, 5, 19, 12, tzinfo=UTC),
            timezone=UTC,
            max_days=366,
            invalid_message="Invalid range.",
            too_large_message="Range too large.",
        )

    assert exc_info.value.code == "date_range_too_large"
    assert exc_info.value.message == "Range too large."
    assert exc_info.value.details == {
        "fromDate": "2025-01-01",
        "toDate": "2026-01-03",
        "maxDays": 366,
    }
