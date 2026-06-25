from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.activity.models import StudentDailyActivity
from backend.auth.models import UserAccount
from backend.chat.schemas import MessageRole, MessageStatus
from backend.instructor.repository import (
    InstructorDashboardRepository,
    InstructorSummaryAggregate,
)
from backend.tests.usage.fixtures import (
    SyncSession,
    create_usage_tables,
    usage_conversation,
    usage_message,
    usage_user,
)
from backend.usage.repository import UserActivityAggregate


@pytest.mark.asyncio
async def test_instructor_repository_returns_empty_dashboard_data() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    repository = InstructorDashboardRepository()

    with Session(engine, expire_on_commit=False) as sync_session:
        session = SyncSession(sync_session)

        summary = await repository.get_summary_metrics(
            session,
            range_start=datetime(2026, 5, 1, tzinfo=UTC),
            range_end=datetime(2026, 5, 2, tzinfo=UTC),
            activity_from_date=date(2026, 5, 1),
            activity_to_date=date(2026, 5, 2),
        )
        roster = await repository.list_student_roster(
            session,
            range_start=datetime(2026, 5, 1, tzinfo=UTC),
            range_end=datetime(2026, 5, 2, tzinfo=UTC),
        )

    assert summary == InstructorSummaryAggregate(active_students=0, questions_asked=0)
    assert roster == []


@pytest.mark.asyncio
async def test_instructor_repository_aggregates_student_dashboard_data() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    repository = InstructorDashboardRepository()

    with Session(engine, expire_on_commit=False) as sync_session:
        maya = usage_user("user_maya", "Maya", "Singh", "student")
        anika = usage_user("user_anika", "Anika", "Brown", "student")
        zara = usage_user("user_zara", "Zara", "Adams", "student")
        admin = usage_user("user_admin", "Admin", "User", "admin")
        instructor = usage_user("user_instructor", "Instructor", "User", "instructor")
        deleted = usage_user(
            "user_deleted",
            "Deleted",
            "Student",
            "student",
            deleted_at=datetime(2026, 5, 1, tzinfo=UTC),
        )
        sync_session.add_all([maya, anika, zara, admin, instructor, deleted])
        sync_session.flush()

        maya_conversation = usage_conversation(maya)
        admin_conversation = usage_conversation(admin)
        instructor_conversation = usage_conversation(instructor)
        deleted_conversation = usage_conversation(deleted)
        sync_session.add_all(
            [
                maya_conversation,
                admin_conversation,
                instructor_conversation,
                deleted_conversation,
            ]
        )
        sync_session.flush()

        sync_session.add_all(
            [
                usage_message(
                    conversation=maya_conversation,
                    user=maya,
                    sequence=1,
                    role=MessageRole.USER,
                    status=MessageStatus.COMPLETED,
                    created_at=datetime(2026, 5, 1, 9, tzinfo=UTC),
                ),
                usage_message(
                    conversation=maya_conversation,
                    user=maya,
                    sequence=2,
                    role=MessageRole.ASSISTANT,
                    status=MessageStatus.BLOCKED,
                    created_at=datetime(2026, 5, 1, 10, tzinfo=UTC),
                ),
                usage_message(
                    conversation=maya_conversation,
                    user=maya,
                    sequence=3,
                    role=MessageRole.USER,
                    status=MessageStatus.BLOCKED,
                    created_at=datetime(2026, 5, 1, 11, tzinfo=UTC),
                ),
                usage_message(
                    conversation=maya_conversation,
                    user=maya,
                    sequence=4,
                    role=MessageRole.USER,
                    status=MessageStatus.COMPLETED,
                    created_at=datetime(2026, 4, 30, 23, 59, tzinfo=UTC),
                ),
                usage_message(
                    conversation=maya_conversation,
                    user=maya,
                    sequence=6,
                    role=MessageRole.USER,
                    status=MessageStatus.COMPLETED,
                    created_at=datetime(2026, 5, 1, 2, tzinfo=UTC),
                ),
                usage_message(
                    conversation=maya_conversation,
                    user=maya,
                    sequence=5,
                    role=MessageRole.ASSISTANT,
                    status=MessageStatus.BLOCKED,
                    created_at=datetime(2026, 5, 2, tzinfo=UTC),
                ),
                usage_message(
                    conversation=admin_conversation,
                    user=admin,
                    sequence=1,
                    role=MessageRole.USER,
                    status=MessageStatus.COMPLETED,
                    created_at=datetime(2026, 5, 1, 12, tzinfo=UTC),
                ),
                usage_message(
                    conversation=instructor_conversation,
                    user=instructor,
                    sequence=1,
                    role=MessageRole.USER,
                    status=MessageStatus.COMPLETED,
                    created_at=datetime(2026, 5, 1, 13, tzinfo=UTC),
                ),
                usage_message(
                    conversation=deleted_conversation,
                    user=deleted,
                    sequence=1,
                    role=MessageRole.USER,
                    status=MessageStatus.COMPLETED,
                    created_at=datetime(2026, 5, 1, 14, tzinfo=UTC),
                ),
                usage_message(
                    conversation=deleted_conversation,
                    user=deleted,
                    sequence=2,
                    role=MessageRole.ASSISTANT,
                    status=MessageStatus.BLOCKED,
                    created_at=datetime(2026, 5, 1, 15, tzinfo=UTC),
                ),
            ]
        )
        sync_session.add_all(
            [
                _activity(maya, date(2026, 5, 1)),
                _activity(anika, date(2026, 5, 1)),
                _activity(zara, date(2026, 5, 2)),
                _activity(deleted, date(2026, 5, 1)),
            ]
        )
        sync_session.commit()

        session = SyncSession(sync_session)
        summary = await repository.get_summary_metrics(
            session,
            range_start=datetime(2026, 5, 1, 4, tzinfo=UTC),
            range_end=datetime(2026, 5, 2, 4, tzinfo=UTC),
            activity_from_date=date(2026, 5, 1),
            activity_to_date=date(2026, 5, 2),
        )
        roster = await repository.list_student_roster(
            session,
            range_start=datetime(2026, 5, 1, 4, tzinfo=UTC),
            range_end=datetime(2026, 5, 2, 4, tzinfo=UTC),
        )

    assert summary == InstructorSummaryAggregate(active_students=2, questions_asked=2)
    assert roster == [
        UserActivityAggregate(
            display_name="Zara Adams",
            access_level="student",
            total_messages_sent=0,
            blocked_requests=0,
            last_activity=None,
        ),
        UserActivityAggregate(
            display_name="Anika Brown",
            access_level="student",
            total_messages_sent=0,
            blocked_requests=0,
            last_activity=None,
        ),
        UserActivityAggregate(
            display_name="Maya Singh",
            access_level="student",
            total_messages_sent=2,
            blocked_requests=2,
            last_activity=datetime(2026, 5, 2),
        ),
    ]


def _create_tables(engine) -> None:
    create_usage_tables(engine)
    StudentDailyActivity.__table__.create(engine)


def _activity(user: UserAccount, activity_date: date) -> StudentDailyActivity:
    return StudentDailyActivity(
        id=uuid4(),
        user_id=user.id,
        activity_date=activity_date,
    )
