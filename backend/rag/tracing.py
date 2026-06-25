from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import SessionFactory
from backend.core.observability import TraceSinkContractError
from backend.rag.repository import RagRepository
from backend.rag.schemas import RagRetrievalLogRecord

SessionFactoryCallable = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class PostgresRagTraceSink:
    def __init__(
        self,
        *,
        rag_index_version: str | None = None,
        session_factory: SessionFactoryCallable = SessionFactory,
        repository: RagRepository | None = None,
    ) -> None:
        self._rag_index_version = rag_index_version
        self._session_factory = session_factory
        self._repository = repository or RagRepository()

    async def record_retrieval(self, record: RagRetrievalLogRecord) -> None:
        if not isinstance(record, RagRetrievalLogRecord):
            raise TraceSinkContractError("record must be a RagRetrievalLogRecord")

        retrieved_chunk_ids = [str(chunk.chunk_id) for chunk in record.chunks]
        scores = [
            {
                "chunk_id": str(chunk.chunk_id),
                "distance": chunk.distance,
                "similarity": chunk.similarity,
            }
            for chunk in record.chunks
        ]

        async with self._session_factory() as session:
            await self._repository.write_retrieval_log(
                session,
                query_text=record.query_text,
                retrieved_chunk_ids=retrieved_chunk_ids,
                scores=scores,
                conversation_id=_optional_uuid(record.conversation_id),
                message_id=_optional_uuid(record.user_message_id),
                rag_index_version=self._rag_index_version,
            )
            await session.commit()


def _optional_uuid(value: UUID | str | None) -> UUID | None:
    return UUID(str(value)) if value is not None else None
