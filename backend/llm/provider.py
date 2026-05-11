from typing import Any

from litellm import acompletion

from backend.llm.config import llm_settings
from backend.llm.schemas import ChatMessage, ProviderResponse, ProviderStreamChunk


class LiteLLMProvider:
    async def complete(self, messages: list[ChatMessage]) -> ProviderResponse:
        response = await acompletion(**_completion_kwargs(messages))

        choice = response.choices[0]
        usage = getattr(response, "usage", None)
        return ProviderResponse(
            content=choice.message.content or "",
            model=getattr(response, "model", None),
            finish_reason=getattr(choice, "finish_reason", None),
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
            total_tokens=getattr(usage, "total_tokens", None),
            raw_response=_serialize_response(response),
        )

    async def stream(self, messages: list[ChatMessage]):
        response = await acompletion(**_completion_kwargs(messages), stream=True)
        async for chunk in response:
            choice = chunk.choices[0] if getattr(chunk, "choices", None) else None
            delta = getattr(choice, "delta", None) if choice is not None else None
            usage = getattr(chunk, "usage", None)
            yield ProviderStreamChunk(
                text=getattr(delta, "content", None) or "",
                model=getattr(chunk, "model", None),
                finish_reason=getattr(choice, "finish_reason", None)
                if choice is not None
                else None,
                prompt_tokens=getattr(usage, "prompt_tokens", None),
                completion_tokens=getattr(usage, "completion_tokens", None),
                total_tokens=getattr(usage, "total_tokens", None),
                raw_response=_serialize_response(chunk),
            )


def _completion_kwargs(messages: list[ChatMessage]) -> dict[str, Any]:
    return {
        "model": llm_settings.model,
        "messages": [
            message.model_dump(mode="json")
            for message in messages
            if message.role.value != "context"
        ],
        "temperature": llm_settings.temperature,
        "max_tokens": llm_settings.max_tokens,
        "timeout": llm_settings.request_timeout_seconds,
        "fallbacks": [llm_settings.fallback_model]
        if llm_settings.fallback_model
        else None,
    }


def _serialize_response(response: Any) -> dict[str, Any] | None:
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")
    if isinstance(response, dict):
        return response
    return None
