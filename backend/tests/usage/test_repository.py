from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.chat.schemas import MessageRole, MessageStatus
from backend.tests.usage.fixtures import (
    SyncSession,
    create_usage_tables,
    usage_conversation,
    usage_message,
    usage_user,
)
from backend.usage.repository import (
    UserActivityAggregate,
    list_admin_user_activity,
    list_student_roster_activity,
)


@pytest.mark.asyncio
async def test_list_admin_user_activity_orders_by_recent_activity_and_pages() -> None:
    engine = create_engine("sqlite:///:memory:")
    create_usage_tables(engine)

    with Session(engine, expire_on_commit=False) as sync_session:
        admin = usage_user("user_admin", "Admin", "User", "admin")
        student = usage_user("user_student", "Student", "User", "student")
        instructor = usage_user("user_instructor", "Instructor", "User", "instructor")
        deleted = usage_user(
            "user_deleted",
            "Deleted",
            "User",
            "student",
            deleted_at=datetime(2026, 5, 1, tzinfo=UTC),
        )
        sync_session.add_all([admin, student, instructor, deleted])
        sync_session.flush()

        admin_conversation = usage_conversation(admin)
        student_conversation = usage_conversation(student)
        deleted_conversation = usage_conversation(deleted)
        sync_session.add_all([admin_conversation, student_conversation, deleted_conversation])
        sync_session.flush()
        sync_session.add_all(
            [
                usage_message(
                    conversation=admin_conversation,
                    user=admin,
                    sequence=1,
                    role=MessageRole.USER,
                    status=MessageStatus.COMPLETED,
                    created_at=datetime(2026, 5, 1, 12, tzinfo=UTC),
                ),
                usage_message(
                    conversation=admin_conversation,
                    user=admin,
                    sequence=2,
                    role=MessageRole.ASSISTANT,
                    status=MessageStatus.BLOCKED,
                    created_at=datetime(2026, 5, 1, 13, tzinfo=UTC),
                ),
                usage_message(
                    conversation=student_conversation,
                    user=student,
                    sequence=1,
                    role=MessageRole.USER,
                    status=MessageStatus.COMPLETED,
                    created_at=datetime(2026, 5, 1, 9, tzinfo=UTC),
                ),
                usage_message(
                    conversation=student_conversation,
                    user=student,
                    sequence=2,
                    role=MessageRole.USER,
                    status=MessageStatus.COMPLETED,
                    created_at=datetime(2026, 5, 1, 11, tzinfo=UTC),
                ),
                usage_message(
                    conversation=deleted_conversation,
                    user=deleted,
                    sequence=1,
                    role=MessageRole.ASSISTANT,
                    status=MessageStatus.BLOCKED,
                    created_at=datetime(2026, 5, 1, 15, tzinfo=UTC),
                ),
            ]
        )
        sync_session.commit()

        rows = await list_admin_user_activity(
            SyncSession(sync_session),
            range_start=datetime(2026, 5, 1, tzinfo=UTC),
            range_end=datetime(2026, 5, 2, tzinfo=UTC),
        )
        paged_rows = await list_admin_user_activity(
            SyncSession(sync_session),
            range_start=datetime(2026, 5, 1, tzinfo=UTC),
            range_end=datetime(2026, 5, 2, tzinfo=UTC),
            limit=2,
            offset=1,
        )

    assert rows == [
        UserActivityAggregate(
            display_name="Admin User",
            access_level="admin",
            total_messages_sent=1,
            blocked_requests=1,
            last_activity=datetime(2026, 5, 1, 13),
        ),
        UserActivityAggregate(
            display_name="Student User",
            access_level="student",
            total_messages_sent=2,
            blocked_requests=0,
            last_activity=datetime(2026, 5, 1, 11),
        ),
        UserActivityAggregate(
            display_name="Instructor User",
            access_level="instructor",
            total_messages_sent=0,
            blocked_requests=0,
            last_activity=None,
        ),
    ]
    assert [row.display_name for row in paged_rows] == ["Student User", "Instructor User"]


@pytest.mark.asyncio
async def test_list_student_roster_activity_filters_students_and_orders_by_name() -> None:
    engine = create_engine("sqlite:///:memory:")
    create_usage_tables(engine)

    with Session(engine, expire_on_commit=False) as sync_session:
        maya = usage_user("user_maya", "Maya", "Singh", "student")
        anika = usage_user("user_anika", "Anika", "Brown", "student")
        admin = usage_user("user_admin", "Admin", "User", "admin")
        deleted = usage_user(
            "user_deleted",
            "Deleted",
            "Student",
            "student",
            deleted_at=datetime(2026, 5, 1, tzinfo=UTC),
        )
        sync_session.add_all([maya, anika, admin, deleted])
        sync_session.flush()

        maya_conversation = usage_conversation(maya)
        admin_conversation = usage_conversation(admin)
        sync_session.add_all([maya_conversation, admin_conversation])
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
                    conversation=admin_conversation,
                    user=admin,
                    sequence=1,
                    role=MessageRole.USER,
                    status=MessageStatus.COMPLETED,
                    created_at=datetime(2026, 5, 1, 11, tzinfo=UTC),
                ),
            ]
        )
        sync_session.commit()

        rows = await list_student_roster_activity(
            SyncSession(sync_session),
            range_start=datetime(2026, 5, 1, tzinfo=UTC),
            range_end=datetime(2026, 5, 2, tzinfo=UTC),
        )

    assert rows == [
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
            total_messages_sent=1,
            blocked_requests=1,
            last_activity=datetime(2026, 5, 1, 10),
        ),
    ]
