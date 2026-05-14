import asyncio

from backend.llm.config import InputGuardrailMode, OutputGuardrailMode, llm_settings
from backend.llm.guardrails import NeMoGuardrailsProvider, NoopGuardrailsProvider
from backend.llm.prompts import build_messages, build_socratic_repair_messages
from backend.llm.provider import LiteLLMProvider
from backend.llm.schemas import (
    GuardrailResult,
    GuardrailsProvider,
    LLMProvider,
    LLMRequest,
    LLMResult,
    ProviderResponse,
    RetrievalResult,
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
        user_message_id,
    ) -> RetrievalResult:
        return RetrievalResult(chunks=[])


class LLMService:
    def __init__(
        self,
        *,
        provider: LLMProvider | None = None,
        guardrails: GuardrailsProvider | None = None,
        input_guardrails: GuardrailsProvider | None = None,
        output_guardrails: GuardrailsProvider | None = None,
        retriever: RetrievalProvider | None = None,
    ) -> None:
        self._provider = provider or LiteLLMProvider()
        self._input_guardrails = (
            guardrails or input_guardrails or _build_input_guardrails()
        )
        self._output_guardrails = (
            guardrails or output_guardrails or _build_output_guardrails()
        )
        self._retriever = retriever or EmptyRetrievalProvider()

    async def complete(self, request: LLMRequest) -> LLMResult:
        retrieval_task = asyncio.create_task(
            self._retriever.retrieve(
                request.content,
                user_id=request.user_id,
                conversation_id=request.conversation_id,
                user_message_id=request.user_message_id,
            ),
        )

        try:
            input_result = await self._input_guardrails.check_input(request.content)
        except asyncio.CancelledError:
            _discard_task_result(retrieval_task)
            raise
        except Exception:
            _discard_task_result(retrieval_task)
            raise

        if input_result.blocked:
            _discard_task_result(retrieval_task)
            provider_response = ProviderResponse(content="")
            output_result = GuardrailResult()
            return _build_result(
                input_result=input_result,
                output_result=output_result,
                provider_response=provider_response,
                retrieval_result=RetrievalResult(chunks=[]),
            )

        retrieval_result = _coerce_retrieval_result(await retrieval_task)
        provider_response = await self._provider.complete(
            build_messages(
                user_input=request.content,
                history=request.history,
                chunks=retrieval_result.chunks,
            ),
        )
        output_result, provider_response = await self._check_output(
            request=request,
            provider_response=provider_response,
            retrieved_context=retrieval_result.chunks,
        )
        return _build_result(
            input_result=input_result,
            output_result=output_result,
            provider_response=provider_response,
            retrieval_result=retrieval_result,
        )

    async def _check_output(
        self,
        *,
        request: LLMRequest,
        provider_response: ProviderResponse,
        retrieved_context: list[RetrievedChunk],
    ) -> tuple[GuardrailResult, ProviderResponse]:
        output_result = await self._output_guardrails.check_output(
            provider_response.content,
            user_input=request.content,
        )
        if not output_result.blocked:
            return output_result, provider_response

        repair_response = await self._provider.complete(
            build_socratic_repair_messages(
                user_input=request.content,
                draft_response=provider_response.content,
                chunks=retrieved_context,
            ),
        )
        repair_result = await self._output_guardrails.check_output(
            repair_response.content,
            user_input=request.content,
        )
        return (
            _with_repair_metadata(repair_result, initial_result=output_result),
            repair_response,
        )


def _build_input_guardrails() -> GuardrailsProvider:
    if not llm_settings.guardrails_enabled:
        return NoopGuardrailsProvider()
    if llm_settings.input_guardrail_mode == InputGuardrailMode.OFF:
        return NoopGuardrailsProvider()
    if llm_settings.input_guardrail_mode == InputGuardrailMode.REGEX:
        return NeMoGuardrailsProvider(llm_settings.regex_guardrails_config_path)
    if llm_settings.guardrails_config_path is None:
        return NoopGuardrailsProvider()
    return NeMoGuardrailsProvider(
        llm_settings.guardrails_config_path,
        model_engine=llm_settings.guardrails_model_engine,
        model=llm_settings.guardrails_model,
    )


def _build_output_guardrails() -> GuardrailsProvider:
    if (
        not llm_settings.guardrails_enabled
        or llm_settings.output_guardrail_mode == OutputGuardrailMode.OFF
        or llm_settings.guardrails_config_path is None
    ):
        return NoopGuardrailsProvider()
    return NeMoGuardrailsProvider(
        llm_settings.guardrails_config_path,
        model_engine=llm_settings.guardrails_model_engine,
        model=llm_settings.guardrails_model,
    )


def _build_result(
    *,
    input_result: GuardrailResult,
    output_result: GuardrailResult,
    provider_response: ProviderResponse,
    retrieval_result: RetrievalResult,
) -> LLMResult:
    content = provider_response.content
    if input_result.blocked:
        content = input_result.reason or "That request was blocked by guardrails."
    elif output_result.blocked:
        content = output_result.reason or "That response was blocked by guardrails."

    return LLMResult(
        content=content,
        retrieval_result=retrieval_result,
        retrieved_context=retrieval_result.chunks,
        input_guardrail_result=input_result,
        output_guardrail_result=output_result,
        provider_response=provider_response,
    )


def _with_repair_metadata(
    result: GuardrailResult,
    *,
    initial_result: GuardrailResult,
) -> GuardrailResult:
    metadata = dict(result.metadata)
    metadata["repairAttempted"] = True
    metadata["repairPassed"] = not result.blocked
    metadata["initialOutputGuardrailResult"] = initial_result.model_dump(
        mode="json",
        by_alias=True,
    )
    return result.model_copy(update={"metadata": metadata})


def _coerce_retrieval_result(
    value: RetrievalResult | list[RetrievedChunk | dict],
) -> RetrievalResult:
    if isinstance(value, RetrievalResult):
        return value
    return RetrievalResult(chunks=[_coerce_retrieved_chunk(chunk) for chunk in value])


def _coerce_retrieved_chunk(value: RetrievedChunk | dict) -> RetrievedChunk:
    if isinstance(value, RetrievedChunk):
        return value
    return RetrievedChunk.model_validate(value)


def _discard_task_result(task: asyncio.Task[RetrievalResult]) -> None:
    task.cancel()
    task.add_done_callback(_consume_task_exception)


def _consume_task_exception(task: asyncio.Task[RetrievalResult]) -> None:
    try:
        task.exception()
    except asyncio.CancelledError:
        pass
