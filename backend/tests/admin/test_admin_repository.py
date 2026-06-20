from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.admin.repository import (
    AdminUsageRepository,
    DailyUsageAggregate,
    UserOverviewAggregate,
)
from backend.auth.models import UserAccount
from backend.chat.models import Conversation, Message
from backend.chat.schemas import MessageRole, MessageStatus


@pytest.mark.asyncio
async def test_cost_component_repository_applies_limit_and_offset() -> None:
    session = CapturingScalarSession()
    repository = AdminUsageRepository()

    rows = await repository.list_cost_components(
        session,
        range_start=datetime(2026, 5, 1, tzinfo=UTC),
        range_end=datetime(2026, 5, 2, tzinfo=UTC),
        limit=25,
        offset=50,
    )

    assert rows == []
    assert session.statement is not None
    assert session.statement._limit_clause.value == 25
    assert session.statement._offset_clause.value == 50


@pytest.mark.asyncio
async def test_user_overview_repository_aggregates_contract_rows() -> None:
    engine = create_engine("sqlite:///:memory:")
    UserAccount.__table__.create(engine)
    Conversation.__table__.create(engine)
    Message.__table__.create(engine)
    repository = AdminUsageRepository()

    with Session(engine, expire_on_commit=False) as sync_session:
        admin_user = UserAccount(
            id=uuid4(),
            clerk_id="user_admin",
            first_name="Admin",
            last_name="User",
            role="admin",
        )
        student_user = UserAccount(
            id=uuid4(),
            clerk_id="user_student",
            first_name="Student",
            last_name="User",
            role="student",
        )
        inactive_alpha = UserAccount(
            id=uuid4(),
            clerk_id="user_alpha",
            first_name="Alpha",
            last_name="User",
            role="instructor",
        )
        inactive_zeta = UserAccount(
            id=uuid4(),
            clerk_id="user_zeta",
            first_name="Zeta",
            last_name="User",
            role="student",
        )
        disabled_user = UserAccount(
            id=uuid4(),
            clerk_id="user_disabled",
            first_name="Disabled",
            last_name="User",
            role="student",
            deleted_at=datetime(2026, 5, 1, tzinfo=UTC),
        )
        sync_session.add_all(
            [admin_user, student_user, inactive_alpha, inactive_zeta, disabled_user]
        )
        sync_session.flush()

        admin_conversation = _conversation(admin_user)
        student_conversation = _conversation(student_user)
        disabled_conversation = _conversation(disabled_user)
        sync_session.add_all([admin_conversation, student_conversation, disabled_conversation])
        sync_session.flush()

        sync_session.add_all(
            [
                _message(
                    conversation=admin_conversation,
                    user=admin_user,
                    sequence=1,
                    role=MessageRole.USER,
                    status=MessageStatus.COMPLETED,
                    created_at=datetime(2026, 5, 1, 12, tzinfo=UTC),
                ),
                _message(
                    conversation=admin_conversation,
                    user=admin_user,
                    sequence=2,
                    role=MessageRole.ASSISTANT,
                    status=MessageStatus.BLOCKED,
                    created_at=datetime(2026, 5, 1, 13, tzinfo=UTC),
                ),
                _message(
                    conversation=student_conversation,
                    user=student_user,
                    sequence=1,
                    role=MessageRole.USER,
                    status=MessageStatus.COMPLETED,
                    created_at=datetime(2026, 4, 30, 23, 59, tzinfo=UTC),
                ),
                _message(
                    conversation=student_conversation,
                    user=student_user,
                    sequence=2,
                    role=MessageRole.USER,
                    status=MessageStatus.COMPLETED,
                    created_at=datetime(2026, 5, 1, 9, tzinfo=UTC),
                ),
                _message(
                    conversation=student_conversation,
                    user=student_user,
                    sequence=3,
                    role=MessageRole.ASSISTANT,
                    status=MessageStatus.BLOCKED,
                    created_at=datetime(2026, 5, 1, 10, tzinfo=UTC),
                ),
                _message(
                    conversation=student_conversation,
                    user=student_user,
                    sequence=4,
                    role=MessageRole.USER,
                    status=MessageStatus.BLOCKED,
                    created_at=datetime(2026, 5, 1, 11, tzinfo=UTC),
                ),
                _message(
                    conversation=student_conversation,
                    user=student_user,
                    sequence=5,
                    role=MessageRole.ASSISTANT,
                    status=MessageStatus.BLOCKED,
                    created_at=datetime(2026, 5, 2, tzinfo=UTC),
                ),
                _message(
                    conversation=disabled_conversation,
                    user=disabled_user,
                    sequence=1,
                    role=MessageRole.ASSISTANT,
                    status=MessageStatus.BLOCKED,
                    created_at=datetime(2026, 5, 1, 15, tzinfo=UTC),
                ),
            ]
        )
        sync_session.commit()

        rows = await repository.list_user_overviews(
            SyncExecuteSession(sync_session),
            range_start=datetime(2026, 5, 1, tzinfo=UTC),
            range_end=datetime(2026, 5, 2, tzinfo=UTC),
        )
        paged_rows = await repository.list_user_overviews(
            SyncExecuteSession(sync_session),
            range_start=datetime(2026, 5, 1, tzinfo=UTC),
            range_end=datetime(2026, 5, 2, tzinfo=UTC),
            limit=2,
            offset=1,
        )

    assert rows == [
        UserOverviewAggregate(
            display_name="Admin User",
            access_level="admin",
            total_messages_sent=1,
            blocked_requests=1,
            last_activity=datetime(2026, 5, 1, 13),
        ),
        UserOverviewAggregate(
            display_name="Student User",
            access_level="student",
            total_messages_sent=2,
            blocked_requests=1,
            last_activity=datetime(2026, 5, 1, 11),
        ),
        UserOverviewAggregate(
            display_name="Alpha User",
            access_level="instructor",
            total_messages_sent=0,
            blocked_requests=0,
            last_activity=None,
        ),
        UserOverviewAggregate(
            display_name="Zeta User",
            access_level="student",
            total_messages_sent=0,
            blocked_requests=0,
            last_activity=None,
        ),
    ]
    assert [row.display_name for row in paged_rows] == ["Student User", "Alpha User"]


@pytest.mark.asyncio
async def test_user_overview_repository_sorts_by_name_parts() -> None:
    engine = create_engine("sqlite:///:memory:")
    UserAccount.__table__.create(engine)
    Conversation.__table__.create(engine)
    Message.__table__.create(engine)
    repository = AdminUsageRepository()

    with Session(engine, expire_on_commit=False) as sync_session:
        gamma_user = UserAccount(
            id=uuid4(),
            clerk_id="user_4",
            first_name="Gamma",
            last_name="User",
            role="student",
        )
        alpha_user = UserAccount(
            id=uuid4(),
            clerk_id="user_2",
            first_name="Alpha",
            last_name="User",
            role="student",
        )
        delta_user = UserAccount(
            id=uuid4(),
            clerk_id="user_3",
            first_name="Delta",
            last_name="User",
            role="student",
        )
        beta_user = UserAccount(
            id=uuid4(),
            clerk_id="user_1",
            first_name="Beta",
            last_name="User",
            role="student",
        )
        sync_session.add_all([beta_user, gamma_user, delta_user, alpha_user])
        sync_session.commit()

        rows = await repository.list_user_overviews(
            SyncExecuteSession(sync_session),
            range_start=datetime(2026, 5, 1, tzinfo=UTC),
            range_end=datetime(2026, 5, 2, tzinfo=UTC),
        )

    assert [row.display_name for row in rows] == [
        "Alpha User",
        "Beta User",
        "Delta User",
        "Gamma User",
    ]


@pytest.mark.asyncio
async def test_usage_metrics_uses_component_tokens() -> None:
    session = SequencedSession(
        execute_results=[
            [
                (
                    2,
                    5,
                    4,
                    1,
                    2,
                    Decimal("1830.2"),
                )
            ],
        ],
        scalar_results=[
            3,
            Decimal("1.2"),
            12,
        ],
    )
    repository = AdminUsageRepository()

    metrics = await repository.get_usage_metrics(
        session,
        range_start=datetime(2026, 5, 1, tzinfo=UTC),
        range_end=datetime(2026, 5, 2, tzinfo=UTC),
    )

    assert metrics.total_users == 2
    assert metrics.total_conversations == 3
    assert metrics.user_queries == 5
    assert metrics.assistant_responses == 4
    assert metrics.failed_responses == 1
    assert metrics.blocked_responses == 2
    assert metrics.total_tokens == 12
    assert metrics.estimated_cost_usd == Decimal("1.2")
    assert metrics.average_latency_ms == Decimal("1830.2")
    assert len(session.scalar_statements) == 3


@pytest.mark.asyncio
async def test_daily_usage_uses_component_tokens_and_zeroes_nulls() -> None:
    session = SequencedSession(
        execute_results=[
            [
                (date(2026, 5, 1), 2, 1),
                (date(2026, 5, 2), 0, 1),
            ],
            [
                (date(2026, 5, 1), 12),
                (date(2026, 5, 3), 5),
                (date(2026, 5, 4), None),
            ],
        ],
    )
    repository = AdminUsageRepository()

    daily_usage = await repository.list_daily_usage(
        session,
        range_start=datetime(2026, 5, 1, tzinfo=UTC),
        range_end=datetime(2026, 5, 5, tzinfo=UTC),
    )

    assert daily_usage == [
        DailyUsageAggregate(
            date=date(2026, 5, 1),
            user_queries=2,
            assistant_responses=1,
            total_tokens=12,
        ),
        DailyUsageAggregate(
            date=date(2026, 5, 2),
            user_queries=0,
            assistant_responses=1,
            total_tokens=0,
        ),
        DailyUsageAggregate(
            date=date(2026, 5, 3),
            user_queries=0,
            assistant_responses=0,
            total_tokens=5,
        ),
        DailyUsageAggregate(
            date=date(2026, 5, 4),
            user_queries=0,
            assistant_responses=0,
            total_tokens=0,
        ),
    ]
    assert len(session.execute_statements) == 2


class SyncExecuteSession:
    def __init__(self, session: Session) -> None:
        self._session = session

    async def execute(self, statement):
        return self._session.execute(statement)


def _conversation(user: UserAccount) -> Conversation:
    return Conversation(
        id=uuid4(),
        user_id=user.id,
        model_profile_key="test-profile",
    )


def _message(
    *,
    conversation: Conversation,
    user: UserAccount,
    sequence: int,
    role: MessageRole,
    status: MessageStatus,
    created_at: datetime,
) -> Message:
    return Message(
        id=uuid4(),
        conversation_id=conversation.id,
        user_id=user.id,
        sequence=sequence,
        role=role.value,
        status=status.value,
        content="test",
        created_at=created_at,
    )


class CapturingScalarSession:
    def __init__(self) -> None:
        self.statement = None

    async def scalars(self, statement):
        self.statement = statement
        return EmptyScalarResult()


class EmptyScalarResult:
    def all(self):
        return []


class SequencedSession:
    def __init__(
        self,
        *,
        execute_results: list[list[tuple]] | None = None,
        scalar_results: list | None = None,
    ) -> None:
        self.execute_results = execute_results or []
        self.scalar_results = scalar_results or []
        self.execute_statements = []
        self.scalar_statements = []

    async def execute(self, statement):
        self.execute_statements.append(statement)
        return SequencedExecuteResult(self.execute_results.pop(0))

    async def scalar(self, statement):
        self.scalar_statements.append(statement)
        return self.scalar_results.pop(0)


class SequencedExecuteResult:
    def __init__(self, rows: list[tuple]) -> None:
        self.rows = rows

    def one(self):
        return self.rows[0]

    def all(self):
        return self.rows
