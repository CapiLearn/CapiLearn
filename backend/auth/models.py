"""SQLAlchemy models for authentication-owned tables."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


def utc_now() -> datetime:
    """Return an aware UTC timestamp for ORM-managed audit columns."""
    return datetime.now(UTC)


class UserAccount(Base):
    """Local account projection keyed by Clerk user id."""

    __tablename__ = "user_account"
    __table_args__ = (
        CheckConstraint(
            "role IN ('student', 'instructor', 'admin')",
            name="role",
        ),
        CheckConstraint("length(trim(first_name)) > 0", name="first_name_not_blank"),
        CheckConstraint("length(trim(last_name)) > 0", name="last_name_not_blank"),
        Index("user_account_clerk_id_idx", "clerk_id", unique=True),
        Index("user_account_role_idx", "role"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    clerk_id: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[str] = mapped_column(String(255), nullable=False)
    clerk_profile_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="student",
        server_default="student",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
