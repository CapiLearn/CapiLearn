from backend.chat.dependencies import get_llm_service, get_rag_retrieval_provider
from backend.rag.config import RagBackend, RagEmbeddingProvider, RagSettings
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
    provider = build_rag_retrieval_provider(
        RagSettings(
            _env_file=None,
            backend=RagBackend.PGVECTOR,
            embedding_provider=RagEmbeddingProvider.OPENAI,
            model_name="text-embedding-3-small",
            OPENAI_API_KEY="test-key",
        )
    )

    assert provider.__class__.__name__ == "PgvectorRagRetrievalProvider"


class FakeRetrievalProvider:
    async def retrieve(self, query, *, user_id, conversation_id, user_message_id):
        return RetrievalResult(chunks=[])
