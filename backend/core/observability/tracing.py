from typing import Any, Protocol


class LLMTraceSink(Protocol):
    async def start_chat_turn(self, metadata: dict[str, Any]) -> None: ...

    async def record_guardrail(self, metadata: dict[str, Any]) -> None: ...

    async def record_retrieval(self, metadata: dict[str, Any]) -> None: ...

    async def record_generation(self, metadata: dict[str, Any]) -> None: ...

    async def record_error(self, metadata: dict[str, Any]) -> None: ...

    async def finish_chat_turn(self, metadata: dict[str, Any]) -> None: ...


class NoopLLMTraceSink:
    async def start_chat_turn(self, metadata: dict[str, Any]) -> None:
        return None

    async def record_guardrail(self, metadata: dict[str, Any]) -> None:
        return None

    async def record_retrieval(self, metadata: dict[str, Any]) -> None:
        return None

    async def record_generation(self, metadata: dict[str, Any]) -> None:
        return None

    async def record_error(self, metadata: dict[str, Any]) -> None:
        return None

    async def finish_chat_turn(self, metadata: dict[str, Any]) -> None:
        return None
