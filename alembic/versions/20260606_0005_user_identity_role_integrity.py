"""Enforce user identity and role integrity.

Revision ID: 20260606_0005
Revises: 20260606_0004
Create Date: 2026-06-06

"""

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa

from alembic import op

revision: str = "20260606_0005"
down_revision: str | None = "20260606_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_LOCAL_DEV_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
LEGACY_LOCAL_DEV_CLERK_ID = "legacy:local-dev-user:00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    connection = op.get_bind()

    _ensure_known_legacy_local_user(connection)
    _assert_valid_roles(connection)
    _assert_no_orphaned_chat_owners(connection)

    op.create_check_constraint(
        op.f("user_account_role_check"),
        "user_account",
        "role IN ('student', 'instructor', 'admin')",
    )
    op.create_foreign_key(
        op.f("conversation_user_id_fkey"),
        "conversation",
        "user_account",
        ["user_id"],
        ["id"],
    )
    op.create_foreign_key(
        op.f("message_user_id_fkey"),
        "message",
        "user_account",
        ["user_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(op.f("message_user_id_fkey"), "message", type_="foreignkey")
    op.drop_constraint(
        op.f("conversation_user_id_fkey"),
        "conversation",
        type_="foreignkey",
    )
    op.drop_constraint(op.f("user_account_role_check"), "user_account", type_="check")


def _ensure_known_legacy_local_user(connection: sa.Connection) -> None:
    if not _legacy_local_chat_rows_exist(connection):
        return
    if _legacy_local_user_exists(connection):
        return

    statement = sa.text(
        """
        INSERT INTO user_account (
            id,
            clerk_id,
            email,
            display_name,
            role,
            created_at,
            updated_at,
            deleted_at
        )
        VALUES (
            :legacy_user_id,
            :legacy_clerk_id,
            NULL,
            'Legacy local dev user',
            'student',
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP,
            NULL
        )
        """
    ).bindparams(
        sa.bindparam("legacy_user_id", type_=sa.Uuid()),
        sa.bindparam("legacy_clerk_id", type_=sa.String()),
    )
    connection.execute(
        statement,
        {
            "legacy_user_id": LEGACY_LOCAL_DEV_USER_ID,
            "legacy_clerk_id": LEGACY_LOCAL_DEV_CLERK_ID,
        },
    )


def _legacy_local_chat_rows_exist(connection: sa.Connection) -> bool:
    statement = sa.text(
        """
        SELECT EXISTS (
            SELECT 1 FROM conversation WHERE user_id = :legacy_user_id
            UNION ALL
            SELECT 1 FROM message WHERE user_id = :legacy_user_id
        )
        """
    ).bindparams(sa.bindparam("legacy_user_id", type_=sa.Uuid()))
    return bool(
        connection.execute(
            statement,
            {"legacy_user_id": LEGACY_LOCAL_DEV_USER_ID},
        ).scalar_one()
    )


def _legacy_local_user_exists(connection: sa.Connection) -> bool:
    statement = sa.text(
        "SELECT EXISTS (SELECT 1 FROM user_account WHERE id = :legacy_user_id)"
    ).bindparams(sa.bindparam("legacy_user_id", type_=sa.Uuid()))
    return bool(
        connection.execute(
            statement,
            {"legacy_user_id": LEGACY_LOCAL_DEV_USER_ID},
        ).scalar_one()
    )


def _assert_valid_roles(connection: sa.Connection) -> None:
    invalid_role_count = connection.execute(
        sa.text(
            """
            SELECT count(*)
            FROM user_account
            WHERE role NOT IN ('student', 'instructor', 'admin')
            """
        )
    ).scalar_one()
    if invalid_role_count:
        raise RuntimeError(
            "Cannot add user_account_role_check: user_account contains invalid roles."
        )


def _assert_no_orphaned_chat_owners(connection: sa.Connection) -> None:
    orphaned_conversation_count = connection.execute(
        sa.text(
            """
            SELECT count(*)
            FROM conversation
            LEFT JOIN user_account ON user_account.id = conversation.user_id
            WHERE user_account.id IS NULL
            """
        )
    ).scalar_one()
    if orphaned_conversation_count:
        raise RuntimeError(
            "Cannot add conversation_user_id_fkey: conversation rows reference "
            "missing user_account ids."
        )

    orphaned_message_count = connection.execute(
        sa.text(
            """
            SELECT count(*)
            FROM message
            LEFT JOIN user_account ON user_account.id = message.user_id
            WHERE user_account.id IS NULL
            """
        )
    ).scalar_one()
    if orphaned_message_count:
        raise RuntimeError(
            "Cannot add message_user_id_fkey: message rows reference missing user_account ids."
        )
