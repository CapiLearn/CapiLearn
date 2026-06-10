from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import SessionFactory
from backend.core.observability import LLMTraceSink
from backend.rag.repository import RagRepository

SessionFactoryCallable = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class PostgresRagTraceSink(LLMTraceSink):
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

    async def _record_retrieval(self, metadata: dict[str, Any]) -> None:
        chunks = metadata.get("chunks") or []
        retrieved_chunk_ids = [
            str(chunk_id) for chunk in chunks if (chunk_id := _chunk_id(chunk)) is not None
        ]
        scores = [
            {
                "chunk_id": str(chunk_id),
                "distance": chunk.get("distance"),
                "similarity": chunk.get("similarity"),
            }
            for chunk in chunks
            if (chunk_id := _chunk_id(chunk)) is not None
        ]

        async with self._session_factory() as session:
            await self._repository.write_retrieval_log(
                session,
                query_text=str(metadata["query_text"]),
                retrieved_chunk_ids=retrieved_chunk_ids,
                scores=scores,
                conversation_id=_optional_uuid(metadata.get("conversation_id")),
                message_id=_optional_uuid(metadata.get("user_message_id")),
                rag_index_version=self._rag_index_version,
            )
            await session.commit()


def _chunk_id(chunk: dict[str, Any]) -> Any:
    return chunk.get("chunk_id") or chunk.get("chunkId")


def _optional_uuid(value: Any) -> UUID | None:
    return UUID(str(value)) if value is not None else None
