"""Helpers for assembling LLM service results."""

from backend.llm.schemas import GuardrailResult, LLMResult, ProviderResponse
from backend.rag.schemas import RetrievalResult


def build_result(
    *,
    input_result: GuardrailResult,
    output_result: GuardrailResult,
    provider_response: ProviderResponse,
    retrieval_result: RetrievalResult,
) -> LLMResult:
    """Build the final result, replacing unsafe content with guardrail reasons."""

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


def with_repair_metadata(
    result: GuardrailResult,
    *,
    initial_result: GuardrailResult,
) -> GuardrailResult:
    """Attach output-repair audit metadata to the final guardrail result."""

    metadata = dict(result.metadata)
    metadata["repairAttempted"] = True
    metadata["repairPassed"] = not result.blocked
    metadata["initialOutputGuardrailResult"] = initial_result.model_dump(
        mode="json",
        by_alias=True,
    )
    return result.model_copy(update={"metadata": metadata})
