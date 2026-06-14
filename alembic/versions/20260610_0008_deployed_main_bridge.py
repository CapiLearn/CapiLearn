"""Bridge deployed main RAG activity revision ancestry.

Revision ID: 20260610_0008
Revises: 20260610_0012
Create Date: 2026-06-10

"""

from collections.abc import Sequence

revision: str = "20260610_0008"
down_revision: str | None = "20260610_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
