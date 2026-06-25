import pytest
from pydantic import ValidationError

from backend.chat.schemas import MessageRole, MessageStatus
from backend.chat.service import ChatService
from backend.llm.schemas import LLMResult, ProviderResponse
from backend.rag.schemas import RetrievedChunk
from backend.tests.chat.service_helpers import (
    FakeChatRepository,
    FakeLLMService,
    FakeSession,
    _conversation,
    _current_user,
    _message,
)


@pytest.mark.asyncio
async def test_create_conversation_persists_validated_used_citations() -> None:
    user = _current_user()
    session = FakeSession()
    repository = FakeChatRepository(user_id=user.id)
    chunks = [
        RetrievedChunk(
            content="State belongs to a component.",
            metadata={
                "chunk_id": "018f7fd2-0f4d-7b62-a542-c1b937dc7468",
                "source_path": "state.md",
                "section_heading": "State",
                "chunk_type": "prose",
            },
        ),
        RetrievedChunk(
            content="Setters schedule updates.",
            metadata={
                "chunk_id": "118f7fd2-0f4d-7b62-a542-c1b937dc7468",
                "source_path": "setters.md",
                "section_heading": "Setters",
                "chunk_type": "prose",
            },
        ),
    ]
    llm_service = FakeLLMService(
        LLMResult(
            content="State is local [1].",
            retrieved_context=chunks,
            provider_response=ProviderResponse(content="raw"),
        )
    )
    service = ChatService(
        session=session,
        user_id=user.id,
        llm_service=llm_service,
        repository=repository,
    )

    response = await service.create_conversation_message("Explain state.")

    assert response.assistant_message.content == "State is local [1]."
    assert [citation.citation_id for citation in response.assistant_message.citations] == ["1"]
    assert response.assistant_message.citations[0].citation_id == "1"
    assert response.assistant_message.citations[0].source_path == "state.md"
    assert response.assistant_message.citations[0].heading == "State"
    assert response.assistant_message.citations[0].chunk_text == "State belongs to a component."
    assert repository.messages[-1].citations == [
        {
            "citationId": "1",
            "sourcePath": "state.md",
            "heading": "State",
            "chunkText": "State belongs to a component.",
        },
    ]
    assert repository.messages[-1].content == "State is local [1]."
    assert not hasattr(repository.messages[-1], "content" + "_parts")


@pytest.mark.asyncio
async def test_list_messages_allows_empty_persisted_citations() -> None:
    user = _current_user()
    session = FakeSession()
    conversation = _conversation(user_id=user.id)
    repository = FakeChatRepository(
        user_id=user.id,
        conversations=[conversation],
        messages=[
            _message(
                conversation=conversation,
                user_id=user.id,
                sequence=1,
                role=MessageRole.ASSISTANT,
                status=MessageStatus.COMPLETED,
                content="No citations here.",
                citations=[],
            )
        ],
    )
    service = ChatService(
        session=session,
        user_id=user.id,
        llm_service=FakeLLMService(LLMResult(content="unused")),
        repository=repository,
    )

    response = await service.list_messages(conversation.id)

    assert response.messages[0].citations == []


@pytest.mark.asyncio
async def test_list_messages_allows_camel_case_persisted_citations() -> None:
    user = _current_user()
    session = FakeSession()
    conversation = _conversation(user_id=user.id)
    repository = FakeChatRepository(
        user_id=user.id,
        conversations=[conversation],
        messages=[
            _message(
                conversation=conversation,
                user_id=user.id,
                sequence=1,
                role=MessageRole.ASSISTANT,
                status=MessageStatus.COMPLETED,
                content="State is local. [1]",
                citations=[
                    {
                        "citationId": "1",
                        "sourcePath": "state.md",
                        "heading": "State",
                        "chunkText": "State belongs to a component.",
                    }
                ],
            )
        ],
    )
    service = ChatService(
        session=session,
        user_id=user.id,
        llm_service=FakeLLMService(LLMResult(content="unused")),
        repository=repository,
    )

    response = await service.list_messages(conversation.id)

    assert response.messages[0].citations[0].citation_id == "1"
    assert response.messages[0].citations[0].source_path == "state.md"
    assert response.messages[0].citations[0].heading == "State"
    assert response.messages[0].citations[0].chunk_text == "State belongs to a component."


@pytest.mark.asyncio
async def test_list_messages_rejects_missing_persisted_citations() -> None:
    user = _current_user()
    session = FakeSession()
    conversation = _conversation(user_id=user.id)
    repository = FakeChatRepository(
        user_id=user.id,
        conversations=[conversation],
        messages=[
            _message(
                conversation=conversation,
                user_id=user.id,
                sequence=1,
                role=MessageRole.ASSISTANT,
                status=MessageStatus.COMPLETED,
                content="Broken persisted state.",
                citations=None,
            )
        ],
    )
    service = ChatService(
        session=session,
        user_id=user.id,
        llm_service=FakeLLMService(LLMResult(content="unused")),
        repository=repository,
    )

    with pytest.raises(ValueError, match="missing required citations"):
        await service.list_messages(conversation.id)


@pytest.mark.asyncio
async def test_list_messages_rejects_snake_case_persisted_citations() -> None:
    user = _current_user()
    session = FakeSession()
    conversation = _conversation(user_id=user.id)
    repository = FakeChatRepository(
        user_id=user.id,
        conversations=[conversation],
        messages=[
            _message(
                conversation=conversation,
                user_id=user.id,
                sequence=1,
                role=MessageRole.ASSISTANT,
                status=MessageStatus.COMPLETED,
                content="Stale citation shape. [1]",
                citations=[
                    {
                        "citation_id": "1",
                        "source_path": "state.md",
                        "heading": "State",
                        "chunk_text": "State belongs to a component.",
                    }
                ],
            )
        ],
    )
    service = ChatService(
        session=session,
        user_id=user.id,
        llm_service=FakeLLMService(LLMResult(content="unused")),
        repository=repository,
    )

    with pytest.raises(ValidationError):
        await service.list_messages(conversation.id)
