from collections.abc import AsyncIterator

from backend.llm.config import llm_settings
from backend.llm.graph import LLMGraph
from backend.llm.guardrails import NeMoGuardrailsProvider, NoopGuardrailsProvider
from backend.llm.orchestration import prepare_input
from backend.llm.prompts import build_messages
from backend.llm.provider import LiteLLMProvider
from backend.llm.schemas import (
    ChatMessage,
    GuardrailResult,
    GuardrailsProvider,
    LLMBlocked,
    LLMDelta,
    LLMProvider,
    LLMRequest,
    LLMResult,
    ProviderResponse,
    ProviderStreamChunk,
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

    async def stream(
        self, request: LLMRequest
    ) -> AsyncIterator[LLMDelta | LLMBlocked | LLMResult]:
        prepared = await prepare_input(
            request=request,
            guardrails=self._guardrails,
            retriever=self._retriever,
        )
        input_result = prepared.input_guardrail_result
        if input_result.blocked:
            yield LLMBlocked(
                reason=input_result.reason or "That request was blocked by guardrails.",
                guardrail_result=input_result,
            )
            return

        retrieved_context = prepared.retrieved_context
        prompt_messages = build_messages(
            user_input=request.content,
            history=request.history,
            chunks=retrieved_context,
        )

        if self._guardrails.has_output_guardrail:
            result = await self._complete_prepared(
                request=request,
                prompt_messages=prompt_messages,
                retrieved_context=retrieved_context,
                input_result=input_result,
            )
            if result.output_guardrail_result.blocked:
                yield LLMBlocked(
                    reason=result.content,
                    guardrail_result=result.output_guardrail_result,
                )
                return

            for chunk in _chunk_text(result.content):
                yield LLMDelta(text=chunk)
            yield result
            return

        accumulated_content = ""
        final_chunk = ProviderStreamChunk()
        async for chunk in self._provider.stream(prompt_messages):
            final_chunk = _merge_stream_metadata(final_chunk, chunk)
            if chunk.text:
                accumulated_content += chunk.text
                yield LLMDelta(text=chunk.text)

        yield _build_result(
            provider_response=ProviderResponse(
                content=accumulated_content,
                model=final_chunk.model,
                finish_reason=final_chunk.finish_reason,
                prompt_tokens=final_chunk.prompt_tokens,
                completion_tokens=final_chunk.completion_tokens,
                total_tokens=final_chunk.total_tokens,
                raw_response=final_chunk.raw_response,
            ),
            retrieved_context=retrieved_context,
            input_result=input_result,
            output_result=GuardrailResult(),
        )

    async def _complete_prepared(
        self,
        *,
        request: LLMRequest,
        prompt_messages: list[ChatMessage],
        retrieved_context: list[RetrievedChunk],
        input_result: GuardrailResult,
    ) -> LLMResult:
        provider_response = await self._provider.complete(prompt_messages)
        output_result = await self._guardrails.check_output(
            provider_response.content,
            user_input=request.content,
        )
        return _build_result(
            provider_response=provider_response,
            retrieved_context=retrieved_context,
            input_result=input_result,
            output_result=output_result,
        )


def _build_guardrails() -> GuardrailsProvider:
    if llm_settings.guardrails_config_path is None:
        return NoopGuardrailsProvider()
    return NeMoGuardrailsProvider(llm_settings.guardrails_config_path)


def _chunk_text(text: str, chunk_size: int = 120) -> list[str]:
    if not text:
        return []
    return [
        text[index : index + chunk_size] for index in range(0, len(text), chunk_size)
    ]


def _merge_stream_metadata(
    previous: ProviderStreamChunk,
    current: ProviderStreamChunk,
) -> ProviderStreamChunk:
    return ProviderStreamChunk(
        model=current.model or previous.model,
        finish_reason=current.finish_reason or previous.finish_reason,
        prompt_tokens=current.prompt_tokens
        if current.prompt_tokens is not None
        else previous.prompt_tokens,
        completion_tokens=current.completion_tokens
        if current.completion_tokens is not None
        else previous.completion_tokens,
        total_tokens=current.total_tokens
        if current.total_tokens is not None
        else previous.total_tokens,
        raw_response=current.raw_response or previous.raw_response,
    )


def _build_result(
    *,
    provider_response: ProviderResponse,
    retrieved_context: list[RetrievedChunk],
    input_result: GuardrailResult,
    output_result: GuardrailResult,
) -> LLMResult:
    content = provider_response.content
    if output_result.blocked:
        content = output_result.reason or "That response was blocked by guardrails."

    return LLMResult(
        content=content,
        citations=[chunk.to_citation() for chunk in retrieved_context],
        retrieved_context=retrieved_context,
        input_guardrail_result=input_result,
        output_guardrail_result=output_result,
        provider_response=provider_response,
    )
