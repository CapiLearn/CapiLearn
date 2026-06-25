"""Date helpers for converting timestamps into activity dates."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

EASTERN_TIME = ZoneInfo("America/New_York")


def eastern_activity_date(value: datetime) -> date:
    """Return the activity date for a timezone-aware timestamp."""
    return as_utc(value).astimezone(EASTERN_TIME).date()


def as_utc(value: datetime) -> datetime:
    """Normalize a timezone-aware timestamp to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Activity timestamps must be timezone-aware.")
    return value.astimezone(UTC)
