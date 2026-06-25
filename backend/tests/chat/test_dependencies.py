import logging
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.auth.schemas import CurrentUser, UserRole
from backend.chat import dependencies as chat_dependencies_module
from backend.chat.dependencies import (
    bind_chat_rate_limit_user,
    get_llm_service,
    get_rag_retrieval_provider,
)
from backend.llm.schemas import GuardrailResult, LLMRequest, ProviderResponse
from backend.rag.config import RagBackend, RagSettings
from backend.rag.models import EMBEDDING_DIMENSIONS
from backend.rag.retrieval import build_rag_retrieval_provider
from backend.rag.schemas import RetrievalResult


def test_get_rag_retrieval_provider_returns_cached_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.rag.retrieval.get_embedding_provider",
        FakeEmbeddingProvider,
    )
    get_rag_retrieval_provider.cache_clear()
    try:
        first = get_rag_retrieval_provider()
        second = get_rag_retrieval_provider()
    finally:
        get_rag_retrieval_provider.cache_clear()

    assert first is second
    assert callable(first.retrieve)


def test_get_llm_service_uses_supplied_retriever() -> None:
    retriever = FakeRetrievalProvider()

    service = get_llm_service(retriever)

    assert service._retriever is retriever


@pytest.mark.asyncio
async def test_get_llm_service_configures_pgvector_trace_sink_best_effort(
    monkeypatch,
    caplog,
) -> None:
    caplog.set_level(logging.WARNING, logger="backend.rag.trace_contracts")
    monkeypatch.setattr(
        chat_dependencies_module,
        "rag_settings",
        RagSettings(
            backend=RagBackend.PGVECTOR,
            write_retrieval_logs=True,
            index_version="fso-2026-06",
        ),
    )
    monkeypatch.setattr(
        chat_dependencies_module,
        "PostgresRagTraceSink",
        FakePostgresRagTraceSink,
    )
    retriever = FakeRetrievalProvider()

    FakePostgresRagTraceSink.instances = []
    service = get_llm_service(retriever)
    service._provider = FakeProvider()
    service._input_guardrails = AllowGuardrails()
    service._output_guardrails = AllowGuardrails()

    result = await service.complete(
        LLMRequest(
            user_id=uuid4(),
            conversation_id=uuid4(),
            user_message_id=uuid4(),
            assistant_message_id=uuid4(),
            content="What is state?",
        )
    )

    assert result.content == "State is stored data."
    assert [sink.rag_index_version for sink in FakePostgresRagTraceSink.instances] == [
        "fso-2026-06"
    ]
    failed_events = [
        record for record in caplog.records if getattr(record, "event", None) == "trace_sink.failed"
    ]
    assert failed_events
    assert failed_events[-1].trace_operation == "record_retrieval"
    assert failed_events[-1].sink_type == "FakePostgresRagTraceSink"


def test_dependency_selector_can_build_pgvector_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.rag.retrieval.get_embedding_provider",
        FakeEmbeddingProvider,
    )

    provider = build_rag_retrieval_provider(RagSettings(backend=RagBackend.PGVECTOR))

    assert provider.__class__.__name__ == "PgvectorRagRetrievalProvider"


@pytest.mark.asyncio
async def test_bind_chat_rate_limit_user_stores_user_on_request_state() -> None:
    user = CurrentUser(
        id=uuid4(),
        clerk_id="user_chat_rate_limit",
        display_name="Rate Limited User",
        role=UserRole.STUDENT,
    )
    request = SimpleNamespace(state=SimpleNamespace())

    resolved_user = await bind_chat_rate_limit_user(request, user)

    assert resolved_user == user
    assert request.state.current_user == user


class FakeRetrievalProvider:
    async def retrieve(self, query, *, user_id, conversation_id, user_message_id):
        return RetrievalResult(chunks=[])


class FakeEmbeddingProvider:
    def embed_query(self, query_text, *, model_name):
        return [0.0] * EMBEDDING_DIMENSIONS


class FakeProvider:
    async def complete(self, messages):
        return ProviderResponse(content="State is stored data.")


class AllowGuardrails:
    async def check_input(self, content):
        return GuardrailResult()

    async def check_output(self, content, *, user_input):
        return GuardrailResult()


class FakePostgresRagTraceSink:
    instances = []

    def __init__(self, *, rag_index_version=None) -> None:
        self.rag_index_version = rag_index_version
        type(self).instances.append(self)

    async def record_retrieval(self, record):
        raise RuntimeError("database unavailable")
