from backend.chat.dependencies import get_llm_service, get_rag_retrieval_provider
from backend.llm.retrieval import RagRetrievalProvider
from backend.llm.schemas import RetrievalResult


def test_get_rag_retrieval_provider_returns_cached_provider() -> None:
    get_rag_retrieval_provider.cache_clear()
    try:
        first = get_rag_retrieval_provider()
        second = get_rag_retrieval_provider()
    finally:
        get_rag_retrieval_provider.cache_clear()

    assert isinstance(first, RagRetrievalProvider)
    assert first is second


def test_get_llm_service_uses_supplied_retriever() -> None:
    retriever = FakeRetrievalProvider()

    service = get_llm_service(retriever)

    assert service._retriever is retriever


class FakeRetrievalProvider:
    async def retrieve(self, query, *, user_id, conversation_id, user_message_id):
        return RetrievalResult(chunks=[])
