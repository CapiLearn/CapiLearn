from uuid import uuid4

import pytest

from backend.llm.schemas import RetrievalProvider
from backend.rag.provider import ChromaRetrievalProvider


@pytest.mark.asyncio
async def test_chroma_retrieval_provider_wraps_sync_retrieve_context() -> None:
    calls = []

    def retrieve_context(question, collection, model, top_k):
        calls.append((question, collection, model, top_k))
        return [
            {
                "content": "Retrieved course chunk.",
                "metadata": {"source_id": "doc_1", "title": "Course Notes"},
                "distance": 0.18,
            }
        ]

    provider = ChromaRetrievalProvider(
        collection="collection",
        model="model",
        retrieve_context_fn=retrieve_context,
        top_k=3,
    )
    retrieval_provider: RetrievalProvider = provider

    result = await retrieval_provider.retrieve(
        "What is a cell?",
        user_id=uuid4(),
        conversation_id=uuid4(),
        user_message_id=uuid4(),
    )

    assert calls == [("What is a cell?", "collection", "model", 3)]
    assert len(result.chunks) == 1
    assert result.chunks[0].content == "Retrieved course chunk."
    assert result.chunks[0].metadata == {
        "source_id": "doc_1",
        "title": "Course Notes",
    }
