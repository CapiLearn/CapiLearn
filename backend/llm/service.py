from backend.llm.config import llm_settings
from backend.llm.graph import LLMGraph
from backend.llm.guardrails import NeMoGuardrailsProvider, NoopGuardrailsProvider
from backend.llm.provider import LiteLLMProvider
from backend.llm.schemas import (
    GuardrailsProvider,
    LLMProvider,
    LLMRequest,
    LLMResult,
    RetrievalProvider,
    RetrievedChunk,
)


class EmptyRetrievalProvider:
    async def retrieve(
        self,
        query: str,
        *,
        user_id,
        conversation_id,
    ) -> list[RetrievedChunk]:
        return []


class LLMService:
    def __init__(
        self,
        *,
        provider: LLMProvider | None = None,
        guardrails: GuardrailsProvider | None = None,
        retriever: RetrievalProvider | None = None,
    ) -> None:
        self._provider = provider or LiteLLMProvider()
        self._guardrails = guardrails or _build_guardrails()
        self._retriever = retriever or EmptyRetrievalProvider()

    async def complete(self, request: LLMRequest) -> LLMResult:
        graph = LLMGraph(
            provider=self._provider,
            guardrails=self._guardrails,
            retriever=self._retriever,
        )
        return await graph.ainvoke(request)


def _build_guardrails() -> GuardrailsProvider:
    if (
        not llm_settings.guardrails_enabled
        or llm_settings.guardrails_config_path is None
    ):
        return NoopGuardrailsProvider()
    return NeMoGuardrailsProvider(
        llm_settings.guardrails_config_path,
        model_engine=llm_settings.guardrails_model_engine,
        model=llm_settings.guardrails_model,
    )
