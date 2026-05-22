from time import perf_counter


def timer_start() -> float:
    return perf_counter()


def elapsed_ms(started_at: float) -> int:
    return max(0, round((perf_counter() - started_at) * 1000))
