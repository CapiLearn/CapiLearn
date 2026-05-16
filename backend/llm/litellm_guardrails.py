from functools import cache
from typing import Any

from langchain_core.callbacks.manager import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.llms import LLM
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import ConfigDict


class LiteLLMGuardrailsChatModel(BaseChatModel):
    model: str
    model_config = ConfigDict(extra="allow")

    @property
    def _llm_type(self) -> str:
        return "litellm_guardrails_chat"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return _identifying_params(
            base=super()._identifying_params,
            model=self.model,
            model_extra=self.model_extra,
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        from litellm import completion

        response = completion(**self._completion_kwargs(messages, stop, kwargs))
        return _chat_result(_response_content(response))

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        from litellm import acompletion

        response = await acompletion(**self._completion_kwargs(messages, stop, kwargs))
        return _chat_result(_response_content(response))

    def _completion_kwargs(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None,
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        return _completion_kwargs(
            model=self.model,
            messages=[_message_to_litellm(message) for message in messages],
            model_extra=self.model_extra,
            stop=stop,
            kwargs=kwargs,
        )


class LiteLLMGuardrailsLLM(LLM):
    model: str
    model_config = ConfigDict(extra="allow")

    @property
    def _llm_type(self) -> str:
        return "litellm_guardrails"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return _identifying_params(
            base=super()._identifying_params,
            model=self.model,
            model_extra=self.model_extra,
        )

    def _call(
        self,
        prompt: str,
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> str:
        from litellm import completion

        response = completion(**self._completion_kwargs(prompt, stop, kwargs))
        return _response_content(response)

    async def _acall(
        self,
        prompt: str,
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> str:
        from litellm import acompletion

        response = await acompletion(**self._completion_kwargs(prompt, stop, kwargs))
        return _response_content(response)

    def _completion_kwargs(
        self,
        prompt: str,
        stop: list[str] | None,
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        return _completion_kwargs(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            model_extra=self.model_extra,
            stop=stop,
            kwargs=kwargs,
        )


@cache
def register_litellm_guardrails_provider() -> None:
    from nemoguardrails.llm.providers import (
        register_chat_provider,
        register_llm_provider,
    )

    register_chat_provider("litellm", LiteLLMGuardrailsChatModel)
    register_llm_provider("litellm", LiteLLMGuardrailsLLM)


def _identifying_params(
    *,
    base: dict[str, Any],
    model: str,
    model_extra: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        **base,
        "model": model,
        **(model_extra or {}),
    }


def _completion_kwargs(
    *,
    model: str,
    messages: list[dict[str, str]],
    model_extra: dict[str, Any] | None,
    stop: list[str] | None,
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    params = dict(model_extra or {})
    params.update(kwargs)
    bound_stop = params.pop("stop", None)
    effective_stop = stop or bound_stop
    if effective_stop:
        params["stop"] = effective_stop
    params.setdefault("temperature", 0)
    return {
        "model": model,
        "messages": messages,
        **params,
    }


def _response_content(response: Any) -> str:
    if isinstance(response, dict):
        choice = _first_choice(response.get("choices"))
        message = choice.get("message") or {}
        return message.get("content") or choice.get("text") or ""

    choice = _first_choice(getattr(response, "choices", None))
    message = getattr(choice, "message", None)
    if message is not None:
        return getattr(message, "content", None) or ""
    return getattr(choice, "text", None) or ""


def _first_choice(choices: Any) -> Any:
    if not choices:
        raise RuntimeError("LLM provider returned a response with no choices.")
    return choices[0]


def _chat_result(content: str) -> ChatResult:
    return ChatResult(
        generations=[
            ChatGeneration(
                message=AIMessage(content=content),
            )
        ]
    )


def _message_to_litellm(message: BaseMessage) -> dict[str, str]:
    role = {
        "human": "user",
        "ai": "assistant",
        "system": "system",
    }.get(message.type, "user")
    content = message.content
    if not isinstance(content, str):
        content = str(content)
    return {"role": role, "content": content}
