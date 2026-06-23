import asyncio
import logging

from backend.core.observability import (
    LLMTraceSink,
    NoopLLMTraceSink,
    elapsed_ms,
    timer_start,
)
from backend.llm.costing import (
    LLMCostRecorder,
    cost_recorder_context,
    generation_component_context,
    guardrail_component_context,
)
from backend.llm.events import LLMEventRecorder
from backend.llm.guardrail_factory import build_input_guardrails, build_output_guardrails
from backend.llm.prompts import build_messages, build_socratic_repair_messages
from backend.llm.provider import LiteLLMProvider
from backend.llm.results import build_result, with_repair_metadata
from backend.llm.schemas import (
    ChatMessage,
    GuardrailResult,
    GuardrailsProvider,
    LLMCostComponent,
    LLMProvider,
    LLMRequest,
    LLMResult,
    ProviderResponse,
)
from backend.rag.schemas import (
    RetrievalProvider,
    RetrievalResult,
    RetrievedChunk,
)
from backend.rag.trace_contracts import NoopRetrievalTraceSink, RetrievalTraceSink

logger = logging.getLogger(__name__)


class LLMServiceError(Exception):
    def __init__(
        self,
        original_exception: Exception,
        *,
        cost_components: list[LLMCostComponent],
    ) -> None:
        super().__init__(str(original_exception))
        self.original_exception = original_exception
        self.cost_components = cost_components


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
        trace_sink: LLMTraceSink | None = None,
        retrieval_trace_sink: RetrievalTraceSink | None = None,
    ) -> None:
        self._provider = provider or LiteLLMProvider()
        self._input_guardrails = guardrails or input_guardrails or build_input_guardrails()
        self._output_guardrails = guardrails or output_guardrails or build_output_guardrails()
        self._retriever = retriever or EmptyRetrievalProvider()
        self._trace_sink = trace_sink or NoopLLMTraceSink()
        self._retrieval_trace_sink = retrieval_trace_sink or NoopRetrievalTraceSink()

    async def complete(self, request: LLMRequest) -> LLMResult:
        recorder = LLMCostRecorder(
            user_id=str(request.user_id),
            conversation_id=str(request.conversation_id),
            user_message_id=str(request.user_message_id),
            assistant_message_id=str(request.assistant_message_id),
        )
        with cost_recorder_context(recorder):
            try:
                result = await self._complete(request)
            except Exception as exc:
                raise LLMServiceError(
                    exc,
                    cost_components=recorder.components,
                ) from exc
        return result.model_copy(update={"cost_components": recorder.components})

    async def _complete(self, request: LLMRequest) -> LLMResult:
        events = LLMEventRecorder(
            trace_sink=self._trace_sink,
            retrieval_trace_sink=self._retrieval_trace_sink,
            logger=logger,
            request=request,
        )
        retrieval_started_at = timer_start()
        retrieval_task = asyncio.create_task(
            self._retriever.retrieve(
                request.content,
                user_id=request.user_id,
                conversation_id=request.conversation_id,
                user_message_id=request.user_message_id,
            ),
        )

        input_guardrail_started_at = timer_start()
        try:
            input_result = await self._input_guardrails.check_input(request.content)
        except asyncio.CancelledError:
            _discard_task_result(retrieval_task)
            raise
        except Exception as exc:
            _discard_task_result(retrieval_task)
            await events.record_guardrail_error(
                stage="input",
                started_at=input_guardrail_started_at,
                exc=exc,
            )
            raise
        await events.record_guardrail_result(
            stage="input",
            started_at=input_guardrail_started_at,
            result=input_result,
        )

        if input_result.blocked:
            _discard_task_result(retrieval_task)
            provider_response = ProviderResponse(content="")
            output_result = GuardrailResult()
            return build_result(
                input_result=input_result,
                output_result=output_result,
                provider_response=provider_response,
                retrieval_result=RetrievalResult(chunks=[]),
            )

        try:
            retrieval_result = await retrieval_task
        except Exception as exc:
            retrieval_result = RetrievalResult(chunks=[])
            await events.record_retrieval_error(
                started_at=retrieval_started_at,
                exc=exc,
                retriever_class=type(self._retriever).__name__,
            )
        else:
            await events.record_retrieval_result(
                started_at=retrieval_started_at,
                result=retrieval_result,
            )

        provider_response = await self._generate(
            events=events,
            messages=build_messages(
                user_input=request.content,
                history=request.history,
                chunks=retrieval_result.chunks,
            ),
            stage="primary",
        )
        output_result, provider_response = await self._check_output(
            events=events,
            request=request,
            provider_response=provider_response,
            retrieved_context=retrieval_result.chunks,
        )
        return build_result(
            input_result=input_result,
            output_result=output_result,
            provider_response=provider_response,
            retrieval_result=retrieval_result,
        )

    async def _check_output(
        self,
        *,
        events: LLMEventRecorder,
        request: LLMRequest,
        provider_response: ProviderResponse,
        retrieved_context: list[RetrievedChunk],
    ) -> tuple[GuardrailResult, ProviderResponse]:
        output_guardrail_started_at = timer_start()
        try:
            with guardrail_component_context("output_guardrail"):
                output_result = await self._output_guardrails.check_output(
                    provider_response.content,
                    user_input=request.content,
                )
        except Exception as exc:
            await events.record_guardrail_error(
                stage="output",
                started_at=output_guardrail_started_at,
                exc=exc,
            )
            raise
        await events.record_guardrail_result(
            stage="output",
            started_at=output_guardrail_started_at,
            result=output_result,
        )
        if not output_result.blocked:
            return output_result, provider_response

        repair_started_at = timer_start()
        repair_response = await self._generate(
            events=events,
            messages=build_socratic_repair_messages(
                user_input=request.content,
                draft_response=provider_response.content,
                chunks=retrieved_context,
            ),
            stage="repair",
        )
        repair_guardrail_started_at = timer_start()
        try:
            with guardrail_component_context("output_repair_guardrail"):
                repair_result = await self._output_guardrails.check_output(
                    repair_response.content,
                    user_input=request.content,
                )
        except Exception as exc:
            await events.record_guardrail_error(
                stage="output_repair",
                started_at=repair_guardrail_started_at,
                exc=exc,
            )
            raise
        await events.record_guardrail_result(
            stage="output_repair",
            started_at=repair_guardrail_started_at,
            result=repair_result,
        )
        await events.record_repair_completed(
            started_at=repair_started_at,
            repair_result=repair_result,
            initial_result=output_result,
        )
        return (
            with_repair_metadata(repair_result, initial_result=output_result),
            repair_response,
        )

    async def _generate(
        self,
        *,
        events: LLMEventRecorder,
        messages: list[ChatMessage],
        stage: str,
    ) -> ProviderResponse:
        started_at = timer_start()
        try:
            component_type = "repair_generation" if stage == "repair" else "main_generation"
            with generation_component_context(component_type):
                provider_response = await self._provider.complete(messages)
        except Exception as exc:
            await events.record_generation_error(
                stage=stage,
                started_at=started_at,
                exc=exc,
            )
            raise

        measured_latency_ms = elapsed_ms(started_at)
        if provider_response.latency_ms is None:
            provider_response.latency_ms = measured_latency_ms
        await events.record_generation_result(
            stage=stage,
            provider_response=provider_response,
        )
        return provider_response


def _discard_task_result(task: asyncio.Task[RetrievalResult]) -> None:
    task.cancel()
    task.add_done_callback(_consume_task_exception)


def _consume_task_exception(task: asyncio.Task[RetrievalResult]) -> None:
    try:
        task.exception()
    except asyncio.CancelledError:
        pass
