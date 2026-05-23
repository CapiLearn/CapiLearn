from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal
from typing import Any

from litellm import acompletion, completion_cost

from backend.core.observability import elapsed_ms, timer_start
from backend.llm.schemas import LLMCostComponent

CompletionCallable = Callable[..., Awaitable[Any]]

_cost_recorder: ContextVar["LLMCostRecorder | None"] = ContextVar(
    "llm_cost_recorder",
    default=None,
)
_generation_component_type: ContextVar[str] = ContextVar(
    "llm_generation_component_type",
    default="main_generation",
)
_guardrail_component_type: ContextVar[str | None] = ContextVar(
    "llm_guardrail_component_type",
    default=None,
)


class LLMCostRecorder:
    def __init__(
        self,
        *,
        user_id: str,
        conversation_id: str,
        user_message_id: str,
        assistant_message_id: str | None,
    ) -> None:
        self._base_fields = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "user_message_id": user_message_id,
            "assistant_message_id": assistant_message_id,
        }
        self._components: list[LLMCostComponent] = []

    @property
    def components(self) -> list[LLMCostComponent]:
        return list(self._components)

    def append(
        self,
        *,
        component_type: str,
        configured_model: str | None,
        response: Any | None,
        status: str,
        latency_ms: int,
        error_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        usage = _response_value(response, "usage")
        choice = _first_choice(response)
        cost, cost_metadata, cost_status = _estimate_cost(response, metadata)
        self._components.append(
            LLMCostComponent(
                **self._base_fields,
                component_order=len(self._components) + 1,
                component_type=component_type,
                attempt_index=1,
                provider=_provider_name(configured_model=configured_model, response=response),
                configured_model=configured_model,
                response_model=_response_value(response, "model"),
                finish_reason=_choice_value(choice, "finish_reason"),
                status=cost_status or status,
                prompt_tokens=_response_value(usage, "prompt_tokens"),
                completion_tokens=_response_value(usage, "completion_tokens"),
                total_tokens=_response_value(usage, "total_tokens"),
                estimated_cost_usd=cost,
                latency_ms=latency_ms,
                error_type=error_type,
                metadata=cost_metadata,
            )
        )


@contextmanager
def cost_recorder_context(recorder: LLMCostRecorder) -> Iterator[None]:
    token = _cost_recorder.set(recorder)
    try:
        yield
    finally:
        _cost_recorder.reset(token)


@contextmanager
def generation_component_context(component_type: str) -> Iterator[None]:
    token = _generation_component_type.set(component_type)
    try:
        yield
    finally:
        _generation_component_type.reset(token)


@contextmanager
def guardrail_component_context(component_type: str) -> Iterator[None]:
    token = _guardrail_component_type.set(component_type)
    try:
        yield
    finally:
        _guardrail_component_type.reset(token)


def current_generation_component_type() -> str:
    return _generation_component_type.get()


def guardrail_component_type(check_type: str) -> str:
    if check_type == "input":
        return "input_guardrail"
    return _guardrail_component_type.get() or "output_guardrail"


async def tracked_acompletion(
    *,
    component_type: str,
    configured_model: str,
    completion: CompletionCallable = acompletion,
    metadata: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    started_at = timer_start()
    try:
        response = await completion(**kwargs)
    except Exception as exc:
        _append_component(
            component_type=component_type,
            configured_model=configured_model,
            response=None,
            status="failed",
            latency_ms=elapsed_ms(started_at),
            error_type=type(exc).__name__,
            metadata=metadata,
        )
        raise

    _append_component(
        component_type=component_type,
        configured_model=configured_model,
        response=response,
        status="completed",
        latency_ms=elapsed_ms(started_at),
        metadata=metadata,
    )
    return response


def _append_component(
    *,
    component_type: str,
    configured_model: str | None,
    response: Any | None,
    status: str,
    latency_ms: int,
    error_type: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    recorder = _cost_recorder.get()
    if recorder is None:
        return
    recorder.append(
        component_type=component_type,
        configured_model=configured_model,
        response=response,
        status=status,
        latency_ms=latency_ms,
        error_type=error_type,
        metadata=metadata,
    )


def _estimate_cost(
    response: Any | None,
    metadata: dict[str, Any] | None,
) -> tuple[Decimal | None, dict[str, Any], str | None]:
    merged_metadata = dict(metadata or {})
    if response is None:
        return None, merged_metadata, None
    try:
        cost = completion_cost(completion_response=response, call_type="acompletion")
    except Exception as exc:
        merged_metadata["costError"] = type(exc).__name__
        merged_metadata["costErrorMessage"] = str(exc)
        return None, merged_metadata, "cost_unavailable"
    return Decimal(str(cost)), merged_metadata, None


def _first_choice(response: Any | None) -> Any | None:
    if response is None:
        return None
    choices = getattr(response, "choices", None)
    if not choices and isinstance(response, dict):
        choices = response.get("choices")
    if not choices:
        return None
    return choices[0]


def _response_value(value: Any | None, key: str) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _choice_value(choice: Any | None, key: str) -> Any:
    return _response_value(choice, key)


def _provider_name(*, configured_model: str | None, response: Any | None) -> str | None:
    hidden_params = getattr(response, "_hidden_params", None)
    if isinstance(hidden_params, dict) and hidden_params.get("custom_llm_provider"):
        return str(hidden_params["custom_llm_provider"])
    if configured_model and "/" in configured_model:
        return configured_model.split("/", 1)[0]
    return None
