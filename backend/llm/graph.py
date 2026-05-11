from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from backend.llm.orchestration import prepare_input
from backend.llm.prompts import build_messages
from backend.llm.schemas import (
    ChatMessage,
    GuardrailResult,
    GuardrailsProvider,
    LLMProvider,
    LLMRequest,
    LLMResult,
    ProviderResponse,
    RetrievalProvider,
    RetrievedChunk,
)


class LLMGraphState(TypedDict, total=False):
    request: LLMRequest
    input_guardrail_result: GuardrailResult
    output_guardrail_result: GuardrailResult
    retrieved_context: list[RetrievedChunk]
    prompt_messages: list[ChatMessage]
    provider_response: ProviderResponse
    result: LLMResult


class LLMGraph:
    def __init__(
        self,
        *,
        provider: LLMProvider,
        guardrails: GuardrailsProvider,
        retriever: RetrievalProvider,
    ) -> None:
        self._provider = provider
        self._guardrails = guardrails
        self._retriever = retriever
        self._graph = self._build_graph()

    async def ainvoke(self, request: LLMRequest) -> LLMResult:
        state = await self._graph.ainvoke({"request": request})
        return state["result"]

    def _build_graph(self):
        workflow = StateGraph(LLMGraphState)
        workflow.add_node("prepare_input", self._prepare_input)
        workflow.add_node("build_prompt", self._build_prompt)
        workflow.add_node("call_model", self._call_model)
        workflow.add_node("check_output", self._check_output)
        workflow.add_node("build_result", self._build_result)

        workflow.add_edge(START, "prepare_input")
        workflow.add_edge("prepare_input", "build_prompt")
        workflow.add_edge("build_prompt", "call_model")
        workflow.add_edge("call_model", "check_output")
        workflow.add_edge("check_output", "build_result")
        workflow.add_edge("build_result", END)
        return workflow.compile()

    async def _prepare_input(self, state: LLMGraphState) -> LLMGraphState:
        request = state["request"]
        prepared = await prepare_input(
            request=request,
            guardrails=self._guardrails,
            retriever=self._retriever,
        )
        return {
            "input_guardrail_result": prepared.input_guardrail_result,
            "retrieved_context": prepared.retrieved_context,
        }

    async def _build_prompt(self, state: LLMGraphState) -> LLMGraphState:
        input_result = state["input_guardrail_result"]
        if input_result.blocked:
            return {"prompt_messages": []}

        request = state["request"]
        return {
            "prompt_messages": build_messages(
                user_input=request.content,
                history=request.history,
                chunks=state["retrieved_context"],
            ),
        }

    async def _call_model(self, state: LLMGraphState) -> LLMGraphState:
        input_result = state["input_guardrail_result"]
        if input_result.blocked:
            return {"provider_response": ProviderResponse(content="")}

        return {
            "provider_response": await self._provider.complete(
                state["prompt_messages"]
            ),
        }

    async def _check_output(self, state: LLMGraphState) -> LLMGraphState:
        input_result = state["input_guardrail_result"]
        if input_result.blocked:
            return {"output_guardrail_result": GuardrailResult()}

        request = state["request"]
        provider_response = state["provider_response"]
        return {
            "output_guardrail_result": await self._guardrails.check_output(
                provider_response.content,
                user_input=request.content,
            ),
        }

    async def _build_result(self, state: LLMGraphState) -> LLMGraphState:
        input_result = state["input_guardrail_result"]
        output_result = state["output_guardrail_result"]
        provider_response = state["provider_response"]
        retrieved_context = state["retrieved_context"]

        content = provider_response.content
        if input_result.blocked:
            content = input_result.reason or "That request was blocked by guardrails."
        elif output_result.blocked:
            content = output_result.reason or "That response was blocked by guardrails."

        return {
            "result": LLMResult(
                content=content,
                citations=[chunk.to_citation() for chunk in retrieved_context],
                retrieved_context=retrieved_context,
                input_guardrail_result=input_result,
                output_guardrail_result=output_result,
                provider_response=provider_response,
            ),
        }
