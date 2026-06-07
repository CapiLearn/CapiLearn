"""Enforce LLM cost component user integrity.

Revision ID: 20260606_0007
Revises: 20260606_0006
Create Date: 2026-06-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260606_0007"
down_revision: str | None = "20260606_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()

    _assert_no_orphaned_cost_component_users(connection)

    op.create_foreign_key(
        op.f("llm_cost_component_user_id_fkey"),
        "llm_cost_component",
        "user_account",
        ["user_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("llm_cost_component_user_id_fkey"),
        "llm_cost_component",
        type_="foreignkey",
    )


def _assert_no_orphaned_cost_component_users(connection: sa.Connection) -> None:
    orphaned_cost_component_count = connection.execute(
        sa.text(
            """
            SELECT count(*)
            FROM llm_cost_component
            LEFT JOIN user_account ON user_account.id = llm_cost_component.user_id
            WHERE user_account.id IS NULL
            """
        )
    ).scalar_one()
    if orphaned_cost_component_count:
        raise RuntimeError(
            "Cannot add llm_cost_component_user_id_fkey: llm_cost_component rows "
            "reference missing user_account ids."
        )
