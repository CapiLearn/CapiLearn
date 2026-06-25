import logging

import pytest
from pydantic import ValidationError

from backend.core.config import Settings
from backend.core.observability import (
    BestEffortLLMTraceSink,
    LLMTraceOperation,
    NoopLLMTraceSink,
    TraceSinkContractError,
)
from backend.core.observability.logging import configure_logging
from backend.core.observability.timing import elapsed_ms


def test_settings_log_level_normalizes_lowercase_debug() -> None:
    settings = Settings(_env_file=None, log_level="debug")

    assert settings.log_level == "DEBUG"


def test_settings_log_level_rejects_invalid_value() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, log_level="INF0")


def test_configure_logging_uses_validated_debug_level() -> None:
    root_logger = logging.getLogger()
    previous_handlers = root_logger.handlers
    previous_level = root_logger.level

    try:
        configure_logging(Settings(_env_file=None, log_level="DEBUG", log_format="plain"))

        assert root_logger.level == logging.DEBUG
    finally:
        root_logger.handlers = previous_handlers
        root_logger.setLevel(previous_level)


def test_elapsed_ms_rounds_positive_elapsed_time(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.core.observability.timing.perf_counter",
        lambda: 1.1234,
    )

    assert elapsed_ms(1.0) == 123


def test_elapsed_ms_clamps_negative_elapsed_time(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.core.observability.timing.perf_counter",
        lambda: 0.999,
    )

    assert elapsed_ms(1.0) == 0


def test_llm_trace_sink_does_not_expose_retrieval_operation() -> None:
    assert not hasattr(NoopLLMTraceSink(), "record_retrieval")


@pytest.mark.asyncio
async def test_best_effort_llm_trace_sink_isolates_delegate_failure(caplog) -> None:
    caplog.set_level(logging.WARNING, logger="backend.core.observability.tracing")
    sink = BestEffortLLMTraceSink(FailingGenerationTraceSink())

    await sink.record(LLMTraceOperation.RECORD_GENERATION, {"event": "test"})

    failed_events = [
        record for record in caplog.records if getattr(record, "event", None) == "trace_sink.failed"
    ]
    assert failed_events
    assert failed_events[-1].trace_operation == "record_generation"
    assert failed_events[-1].sink_type == "FailingGenerationTraceSink"


@pytest.mark.asyncio
async def test_best_effort_llm_trace_sink_preserves_contract_errors() -> None:
    sink = BestEffortLLMTraceSink(ContractErrorTraceSink())

    with pytest.raises(TraceSinkContractError, match="bad metadata"):
        await sink.record(LLMTraceOperation.RECORD_GENERATION, {})


class FailingGenerationTraceSink(NoopLLMTraceSink):
    async def record(self, operation, metadata):
        raise RuntimeError("trace sink unavailable")


class ContractErrorTraceSink(NoopLLMTraceSink):
    async def record(self, operation, metadata):
        raise TraceSinkContractError("bad metadata")
