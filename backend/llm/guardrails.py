from pathlib import Path
from typing import Any

from backend.llm.litellm_guardrails import register_litellm_guardrails_provider
from backend.llm.schemas import GuardrailResult


class NoopGuardrailsProvider:
    has_output_guardrail = False

    async def check_input(self, content: str) -> GuardrailResult:
        return GuardrailResult(metadata={"checked_content_length": len(content)})

    async def check_output(self, content: str, *, user_input: str) -> GuardrailResult:
        return GuardrailResult(
            metadata={
                "checked_content_length": len(content),
                "user_input_length": len(user_input),
            },
        )


class NeMoGuardrailsProvider:
    has_output_guardrail = True

    def __init__(
        self,
        config_path: Path,
        *,
        model_engine: str | None = None,
        model: str | None = None,
    ) -> None:
        from nemoguardrails import LLMRails, RailsConfig

        register_litellm_guardrails_provider()
        config = RailsConfig.from_path(str(config_path))
        if model_engine is not None or model is not None:
            _configure_main_model(config, model_engine=model_engine, model=model)
        self._rails = LLMRails(config)

    async def check_input(self, content: str) -> GuardrailResult:
        from nemoguardrails.rails.llm.options import RailType

        result = await self._rails.check_async(
            [{"role": "user", "content": content}],
            rail_types=[RailType.INPUT],
        )
        return _to_guardrail_result(result)

    async def check_output(self, content: str, *, user_input: str) -> GuardrailResult:
        from nemoguardrails.rails.llm.options import RailType

        result = await self._rails.check_async(
            [
                {"role": "user", "content": user_input},
                {"role": "assistant", "content": content},
            ],
            rail_types=[RailType.OUTPUT],
        )
        return _to_guardrail_result(result)


def _to_guardrail_result(result: Any) -> GuardrailResult:
    from nemoguardrails.rails.llm.options import RailStatus

    status = getattr(result, "status", None)
    rail = getattr(result, "rail", None)
    content = getattr(result, "content", None)
    return GuardrailResult(
        blocked=status == RailStatus.BLOCKED,
        reason="Message blocked by guardrails."
        if status == RailStatus.BLOCKED
        else None,
        rail=str(rail) if rail is not None else None,
        metadata={
            "status": str(status) if status is not None else None,
            "content": content,
        },
    )


def _configure_main_model(
    config: Any,
    *,
    model_engine: str | None,
    model: str | None,
) -> None:
    for index, configured_model in enumerate(config.models):
        if configured_model.type != "main":
            continue
        config.models[index] = configured_model.model_copy(
            update={
                "engine": model_engine or configured_model.engine,
                "model": model or configured_model.model,
            },
        )
        return
