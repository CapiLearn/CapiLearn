"""Bridge deployed beta revision ancestry.

Revision ID: 20260612_0009
Revises: 20260610_0008
Create Date: 2026-06-12

"""

from collections.abc import Sequence

revision: str = "20260612_0009"
down_revision: str | None = "20260610_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
