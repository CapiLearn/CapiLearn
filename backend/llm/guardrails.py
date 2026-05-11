from pathlib import Path
from typing import Any

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

    def __init__(self, config_path: Path) -> None:
        from nemoguardrails import LLMRails, RailsConfig

        config = RailsConfig.from_path(str(config_path))
        self._rails = LLMRails(config)

    async def check_input(self, content: str) -> GuardrailResult:
        result = await self._rails.check_async(
            [{"role": "user", "content": content}],
        )
        return _to_guardrail_result(result)

    async def check_output(self, content: str, *, user_input: str) -> GuardrailResult:
        result = await self._rails.check_async(
            [
                {"role": "user", "content": user_input},
                {"role": "assistant", "content": content},
            ],
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
