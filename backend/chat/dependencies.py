from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, status

from backend.chat.schemas import CurrentUser
from backend.chat.service import ChatService
from backend.core.config import settings
from backend.core.database import DbSession
from backend.core.exceptions import ApiError
from backend.llm.service import LLMService
from backend.rag.config import rag_settings
from backend.rag.retrieval import build_rag_retrieval_provider
from backend.rag.schemas import RetrievalProvider


async def get_current_user(
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
    x_user_email: Annotated[str | None, Header(alias="X-User-Email")] = None,
) -> CurrentUser:
    if x_user_id is None:
        return CurrentUser(id=settings.local_dev_user_id, email=x_user_email)

    try:
        user_id = UUID(x_user_id)
    except ValueError as exc:
        raise ApiError(
            code="invalid_user_header",
            message="X-User-Id must be a valid UUID.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        ) from exc

    return CurrentUser(id=user_id, email=x_user_email)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


@lru_cache(maxsize=1)
def get_rag_retrieval_provider() -> RetrievalProvider:
    return build_rag_retrieval_provider(rag_settings)


RetrievalProviderDep = Annotated[
    RetrievalProvider,
    Depends(get_rag_retrieval_provider),
]


def get_llm_service(retriever: RetrievalProviderDep) -> LLMService:
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
