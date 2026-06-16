from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request

from backend.auth.dependencies import CurrentUserDep
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
    return build_rag_retrieval_provider(rag_settings)


RetrievalProviderDep = Annotated[
    RetrievalProvider,
    Depends(get_rag_retrieval_provider),
]


def get_llm_service(retriever: RetrievalProviderDep) -> LLMService:
    retrieval_trace_sink = None
    if rag_settings.backend == RagBackend.PGVECTOR and rag_settings.write_retrieval_logs:
        retrieval_trace_sink = BestEffortRetrievalTraceSink(
            PostgresRagTraceSink(rag_index_version=rag_settings.index_version)
        )
    return LLMService(retriever=retriever, retrieval_trace_sink=retrieval_trace_sink)


LLMServiceDep = Annotated[LLMService, Depends(get_llm_service)]


async def bind_chat_rate_limit_user(
    request: Request,
    current_user: CurrentUserDep,
) -> CurrentUser:
    request.state.current_user = current_user
    return current_user


ChatRateLimitUserDep = Annotated[CurrentUser, Depends(bind_chat_rate_limit_user)]


def get_chat_service(
    session: DbSession,
    current_user: CurrentUserDep,
    llm_service: LLMServiceDep,
) -> ChatService:
    return ChatService(
        session=session,
        current_user=current_user,
        llm_service=llm_service,
    )


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
