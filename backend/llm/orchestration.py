import asyncio
from dataclasses import dataclass

from backend.llm.schemas import (
    GuardrailResult,
    GuardrailsProvider,
    LLMRequest,
    RetrievalProvider,
    RetrievedChunk,
)


@dataclass(frozen=True)
class PreparedInput:
    input_guardrail_result: GuardrailResult
    retrieved_context: list[RetrievedChunk]


async def prepare_input(
    *,
    request: LLMRequest,
    guardrails: GuardrailsProvider,
    retriever: RetrievalProvider,
) -> PreparedInput:
    retrieval_task = asyncio.create_task(
        retriever.retrieve(
            request.content,
            user_id=request.user_id,
            conversation_id=request.conversation_id,
        ),
    )

    try:
        input_result = await guardrails.check_input(request.content)
    except asyncio.CancelledError:
        _discard_task_result(retrieval_task)
        raise
    except Exception:
        _discard_task_result(retrieval_task)
        raise
    if input_result.blocked:
        _discard_task_result(retrieval_task)
        return PreparedInput(
            input_guardrail_result=input_result,
            retrieved_context=[],
        )

    return PreparedInput(
        input_guardrail_result=input_result,
        retrieved_context=await retrieval_task,
    )


def _discard_task_result(task: asyncio.Task[list[RetrievedChunk]]) -> None:
    task.add_done_callback(_consume_task_exception)


def _consume_task_exception(task: asyncio.Task[list[RetrievedChunk]]) -> None:
    try:
        task.exception()
    except asyncio.CancelledError:
        pass
