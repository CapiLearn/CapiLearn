"""LiteLLM-backed chat completion provider for the LLM service."""

import asyncio
import logging
from typing import Any

from litellm import (
    APIConnectionError,
    InternalServerError,
    RateLimitError,
    ServiceUnavailableError,
    acompletion,
)

from backend.core.observability import elapsed_ms, timer_start
from backend.llm.config import llm_settings
from backend.llm.costing import current_generation_component_type, tracked_acompletion
from backend.llm.schemas import ChatMessage, ProviderResponse

logger = logging.getLogger(__name__)

_TRANSIENT_PROVIDER_ERRORS = (
    APIConnectionError,
    InternalServerError,
    RateLimitError,
    ServiceUnavailableError,
)


class ProviderResponseError(RuntimeError):
    """Raised when the provider returns a structurally invalid success response."""


class LiteLLMProvider:
    """Provider adapter that turns CapiLearn chat messages into LiteLLM calls."""

    async def complete(self, messages: list[ChatMessage]) -> ProviderResponse:
        """Return a normalized provider response, retrying transient provider errors."""

        last_error: Exception | None = None
        max_attempts = llm_settings.max_retries + 1
        for attempt in range(1, max_attempts + 1):
            try:
                return await self._complete_once(messages, attempt_index=attempt)
            except _TRANSIENT_PROVIDER_ERRORS as exc:
                last_error = exc
                if attempt >= max_attempts:
                    break
                logger.warning(
                    "Retrying transient LLM provider failure.",
                    extra={
                        "event": "llm.provider.retry",
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "max_retries": llm_settings.max_retries,
                        "error_type": type(exc).__name__,
                        "model": llm_settings.model,
                    },
                )
                await asyncio.sleep(llm_settings.retry_backoff_seconds)

        if last_error is not None:
            raise last_error
        raise RuntimeError("LLM provider retry loop exited without a response.")

    async def _complete_once(
        self,
        messages: list[ChatMessage],
        *,
        attempt_index: int,
    ) -> ProviderResponse:
        """Execute one provider attempt and validate the successful response shape."""

        started_at = timer_start()
        kwargs = {
            "model": llm_settings.model,
            "messages": [message.model_dump(mode="json") for message in messages],
            "max_tokens": llm_settings.max_tokens,
            "timeout": llm_settings.request_timeout_seconds,
            "fallbacks": [llm_settings.fallback_model] if llm_settings.fallback_model else None,
        }
        if llm_settings.temperature is not None:
            kwargs["temperature"] = llm_settings.temperature
        response = await tracked_acompletion(
            component_type=current_generation_component_type(),
            configured_model=llm_settings.model,
            attempt_index=attempt_index,
            completion=acompletion,
            validate_response=_validate_provider_response,
            **kwargs,
        )

        choice = _first_choice(response)
        content = _message_content(choice)
        usage = getattr(response, "usage", None)
        return ProviderResponse(
            content=content,
            model=getattr(response, "model", None),
            finish_reason=getattr(choice, "finish_reason", None),
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
            total_tokens=getattr(usage, "total_tokens", None),
            latency_ms=elapsed_ms(started_at),
        )


def _first_choice(response: Any) -> Any:
    choices = getattr(response, "choices", None)
    if not choices:
        raise RuntimeError("LLM provider returned a response with no choices.")
    return choices[0]


def _validate_provider_response(response: Any) -> None:
    _message_content(_first_choice(response))


def _message_content(choice: Any) -> str:
    message = getattr(choice, "message", None)
    content = getattr(message, "content", None)
    if content is None:
        raise ProviderResponseError(
            "LLM provider returned a response choice with no message content."
        )
    if not isinstance(content, str):
        raise ProviderResponseError(
            "LLM provider returned a response choice with non-text message content."
        )
    return content
