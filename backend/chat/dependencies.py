"""FastAPI dependency providers for the chat API."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request

from backend.auth.dependencies import StudentUserDep
from backend.auth.schemas import CurrentUser
from backend.chat.service import ChatService
from backend.core.database import DbSession
from backend.llm.service import LLMService
from backend.rag.config import RagBackend, rag_settings
from backend.rag.retrieval import build_rag_retrieval_provider
from backend.rag.schemas import RetrievalProvider
from backend.rag.trace_contracts import BestEffortRetrievalTraceSink
from backend.rag.tracing import PostgresRagTraceSink


@lru_cache(maxsize=1)
def get_rag_retrieval_provider() -> RetrievalProvider:
    """Build the process-local retrieval provider used by chat completions."""
    return build_rag_retrieval_provider(rag_settings)


RetrievalProviderDep = Annotated[
    RetrievalProvider,
    Depends(get_rag_retrieval_provider),
]


def get_llm_service(retriever: RetrievalProviderDep) -> LLMService:
    """Create an LLM service wired with retrieval and optional RAG tracing."""
    retrieval_trace_sink = None
    if rag_settings.backend == RagBackend.PGVECTOR and rag_settings.write_retrieval_logs:
        # Retrieval traces are observational data, so failures must not block chat turns.
        retrieval_trace_sink = BestEffortRetrievalTraceSink(
            PostgresRagTraceSink(rag_index_version=rag_settings.index_version)
        )
    return LLMService(retriever=retriever, retrieval_trace_sink=retrieval_trace_sink)


LLMServiceDep = Annotated[LLMService, Depends(get_llm_service)]


async def bind_chat_rate_limit_user(
    request: Request,
    current_user: StudentUserDep,
) -> CurrentUser:
    """Expose the authenticated user to the shared chat rate-limit key function."""
    request.state.current_user = current_user
    return current_user


ChatRateLimitUserDep = Annotated[CurrentUser, Depends(bind_chat_rate_limit_user)]


def get_chat_service(
    session: DbSession,
    current_user: StudentUserDep,
    llm_service: LLMServiceDep,
) -> ChatService:
    """Create the per-request chat service for the authenticated student."""
    return ChatService(
        session=session,
        user_id=current_user.id,
        llm_service=llm_service,
    )


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
