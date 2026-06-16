from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.auth.schemas import CurrentUser, UserRole
from backend.chat.dependencies import (
    bind_chat_rate_limit_user,
    get_llm_service,
    get_rag_retrieval_provider,
)
from backend.rag.config import RagBackend, RagSettings
from backend.rag.retrieval import build_rag_retrieval_provider
from backend.rag.schemas import RetrievalResult


def test_get_rag_retrieval_provider_returns_cached_provider() -> None:
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


def test_dependency_selector_can_build_pgvector_provider() -> None:
    provider = build_rag_retrieval_provider(RagSettings(backend=RagBackend.PGVECTOR))

    assert provider.__class__.__name__ == "PgvectorRagRetrievalProvider"


@pytest.mark.asyncio
async def test_bind_chat_rate_limit_user_stores_user_on_request_state() -> None:
    user = CurrentUser(
        id=uuid4(),
        clerk_id="user_chat_rate_limit",
        role=UserRole.STUDENT,
    )
    request = SimpleNamespace(state=SimpleNamespace())

    resolved_user = await bind_chat_rate_limit_user(request, user)

    assert resolved_user == user
    assert request.state.current_user == user


class FakeRetrievalProvider:
    async def retrieve(self, query, *, user_id, conversation_id, user_message_id):
        return RetrievalResult(chunks=[])
