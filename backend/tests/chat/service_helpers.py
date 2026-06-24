from datetime import UTC, datetime
from uuid import uuid4

from backend.auth.schemas import CurrentUser, UserRole
from backend.chat.models import Conversation, Message
from backend.chat.repository import MessageSequenceConflictError
from backend.chat.schemas import ConversationStatus, MessageRole, MessageStatus
from backend.chat.service import ChatService
from backend.core.observability import LLMTraceSink, NoopLLMTraceSink
from backend.llm.schemas import LLMCostComponent, LLMResult, ProviderResponse
from backend.llm.service import LLMServiceError

_DEFAULT_CITATIONS = object()


def _current_user() -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        clerk_id=f"user_{uuid4().hex}",
        display_name="Test User",
        role=UserRole.STUDENT,
    )


class FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.rollback_count = 0

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1


class FakeChatRepository:
    def __init__(
        self,
        *,
        user_id,
        conversations: list[Conversation] | None = None,
        messages: list[Message] | None = None,
    ) -> None:
        self.user_id = user_id
        self.conversations = conversations or []
        self.messages = messages or []
        self.cost_components = []

    async def create_conversation(
        self,
        session,
        *,
        user_id,
        title,
        model_profile_key,
        model_profile_version,
        guardrails_config_id,
        rag_index_version,
    ):
        conversation = _conversation(
            user_id=user_id,
            title=title,
            model_profile_key=model_profile_key,
            model_profile_version=model_profile_version,
            guardrails_config_id=guardrails_config_id,
            rag_index_version=rag_index_version,
        )
        self.conversations.append(conversation)
        return conversation

    async def get_conversation(self, session, *, conversation_id, user_id):
        for conversation in self.conversations:
            if conversation.id == conversation_id and conversation.user_id == user_id:
                return conversation
        return None

    async def list_messages(self, session, *, conversation_id, user_id):
        return [
            message
            for message in self.messages
            if message.conversation_id == conversation_id and message.user_id == user_id
        ]

    async def create_turn_messages(
        self,
        session,
        *,
        conversation,
        user_id,
        content,
    ):
        next_sequence = (
            len([item for item in self.messages if item.conversation_id == conversation.id]) + 1
        )
        user_message = _message(
            conversation=conversation,
            user_id=user_id,
            sequence=next_sequence,
            role=MessageRole.USER,
            status=MessageStatus.COMPLETED,
            content=content,
        )
        assistant_message = _message(
            conversation=conversation,
            user_id=user_id,
            sequence=next_sequence + 1,
            role=MessageRole.ASSISTANT,
            status=MessageStatus.PENDING,
            content="",
        )
        self.messages.extend([user_message, assistant_message])
        return user_message, assistant_message

    async def create_llm_cost_components(self, session, *, components):
        self.cost_components.extend(components)


class ConflictingChatRepository(FakeChatRepository):
    def __init__(self, *, user_id, exc: Exception | None = None) -> None:
        super().__init__(user_id=user_id)
        self.exc = exc or MessageSequenceConflictError()

    async def create_turn_messages(
        self,
        session,
        *,
        conversation,
        user_id,
        content,
    ):
        raise self.exc


class FakeLLMService:
    def __init__(self, result: LLMResult) -> None:
        self.result = result
        self.requests = []

    async def complete(self, request):
        self.requests.append(request)
        return self.result


class CostedLLMService:
    def __init__(self) -> None:
        self.requests = []
        self.result = LLMResult(content="")

    async def complete(self, request):
        self.requests.append(request)
        self.result = LLMResult(
            content="Cells are small units.",
            provider_response=ProviderResponse(content="Cells are small units."),
            cost_components=[
                LLMCostComponent(
                    user_id=request.user_id,
                    conversation_id=request.conversation_id,
                    user_message_id=request.user_message_id,
                    assistant_message_id=request.assistant_message_id,
                    component_order=1,
                    component_type="main_generation",
                    status="completed",
                    estimated_cost_usd="0.001000000000",
                )
            ],
        )
        return self.result


class FailingLLMService:
    async def complete(self, request):
        raise RuntimeError("provider unavailable")


class FailingCostedLLMService:
    def __init__(self) -> None:
        self.cost_components = []

    async def complete(self, request):
        self.cost_components = [
            LLMCostComponent(
                user_id=request.user_id,
                conversation_id=request.conversation_id,
                user_message_id=request.user_message_id,
                assistant_message_id=request.assistant_message_id,
                component_order=1,
                component_type="main_generation",
                status="failed",
                error_type="RuntimeError",
            )
        ]
        raise LLMServiceError(
            RuntimeError("provider unavailable"),
            cost_components=self.cost_components,
        )


class IncompleteTraceSink(LLMTraceSink):
    pass


class FailingTraceSink(NoopLLMTraceSink):
    async def record(self, operation, metadata):
        raise RuntimeError("trace sink unavailable")


def _new_conversation_service(llm_result: LLMResult):
    user = _current_user()
    session = FakeSession()
    repository = FakeChatRepository(user_id=user.id)
    service = ChatService(
        session=session,
        user_id=user.id,
        llm_service=FakeLLMService(llm_result),
        repository=repository,
    )
    return service, session, repository


def _service_with_existing_message(
    *,
    role: MessageRole,
    status: MessageStatus,
    content: str | None,
    sequence: int = 1,
    history_context=None,
    llm_result: LLMResult | None = None,
):
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
                sequence=sequence,
                role=role,
                status=status,
                content=content,
                history_context=history_context,
            ),
        ],
    )
    llm_service = FakeLLMService(llm_result or LLMResult(content="unused"))
    service = ChatService(
        session=session,
        user_id=user.id,
        llm_service=llm_service,
        repository=repository,
    )
    return service, session, repository, llm_service, conversation


def _events(records, event: str):
    return [record for record in records if getattr(record, "event", None) == event]


def _conversation(
    *,
    user_id,
    title: str | None = "Existing title",
    model_profile_key: str = "model",
    model_profile_version: str | None = None,
    guardrails_config_id: str | None = None,
    rag_index_version: str | None = None,
) -> Conversation:
    now = datetime.now(UTC)
    return Conversation(
        id=uuid4(),
        user_id=user_id,
        title=title,
        status=ConversationStatus.ACTIVE.value,
        model_profile_key=model_profile_key,
        model_profile_version=model_profile_version,
        guardrails_config_id=guardrails_config_id,
        rag_index_version=rag_index_version,
        created_at=now,
        updated_at=now,
    )


def _message(
    *,
    conversation: Conversation,
    user_id,
    sequence: int,
    role: MessageRole,
    status: MessageStatus,
    content: str | None,
    history_context: list[dict] | None = None,
    citations=_DEFAULT_CITATIONS,
) -> Message:
    if citations is _DEFAULT_CITATIONS:
        citations = []

    return Message(
        id=uuid4(),
        conversation_id=conversation.id,
        user_id=user_id,
        sequence=sequence,
        role=role.value,
        status=status.value,
        content=content,
        history_context=history_context or [],
        citations=citations,
        created_at=datetime.now(UTC),
    )
