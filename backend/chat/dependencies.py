from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from backend.auth.dependencies import CurrentUserDep
from backend.chat.service import ChatService
from backend.core.database import DbSession
from backend.llm.retrieval import RagRetrievalProvider
from backend.llm.schemas import RetrievalProvider
from backend.llm.service import LLMService


@lru_cache(maxsize=1)
def get_rag_retrieval_provider() -> RetrievalProvider:
    return RagRetrievalProvider()


RagRetrievalProviderDep = Annotated[
    RetrievalProvider,
    Depends(get_rag_retrieval_provider),
]


def get_llm_service(retriever: RagRetrievalProviderDep) -> LLMService:
    return LLMService(retriever=retriever)


LLMServiceDep = Annotated[LLMService, Depends(get_llm_service)]


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
