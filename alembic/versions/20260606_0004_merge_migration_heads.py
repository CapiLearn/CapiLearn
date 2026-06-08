"""Merge RAG and LLM cost migration heads.

Revision ID: 20260606_0004
Revises: 20260519_0002, 20260523_0003
Create Date: 2026-06-06

"""

from collections.abc import Sequence

revision: str = "20260606_0004"
down_revision: str | Sequence[str] | None = (
    "20260519_0002",
    "20260523_0003",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
