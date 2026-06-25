"""Monotonic timing helpers for latency measurements."""

from time import perf_counter


def timer_start() -> float:
    """Return a monotonic timestamp suitable for elapsed_ms."""
    return perf_counter()


def elapsed_ms(started_at: float) -> int:
    """Return non-negative elapsed milliseconds since started_at."""
    return max(0, round((perf_counter() - started_at) * 1000))
