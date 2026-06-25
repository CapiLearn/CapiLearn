"""Services for applying Clerk user webhooks to local auth state."""

from datetime import UTC, datetime
from typing import Any

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.profile_projection import profile_from_clerk_user
from backend.auth.repository import UserAccountRepository
from backend.core.exceptions import ApiError

UPSERT_USER_EVENTS = {"user.created", "user.updated"}


class ClerkWebhookService:
    """Project Clerk user lifecycle events into the local user account table."""

    def __init__(self, repository: UserAccountRepository | None = None) -> None:
        self._repository = repository or UserAccountRepository()

    async def handle_event(self, session: AsyncSession, event: dict[str, Any]) -> None:
        """Apply supported Clerk user events and ignore unrelated event types."""
        event_type = event.get("type")
        data = event.get("data")

        if event_type in UPSERT_USER_EVENTS:
            data = _require_event_data(data, event_type=event_type)
            profile = profile_from_clerk_user(data)
            await self._repository.upsert_from_clerk_profile(
                session,
                clerk_id=profile.clerk_id,
                first_name=profile.first_name,
                last_name=profile.last_name,
                clerk_profile_updated_at=profile.clerk_profile_updated_at,
            )
            return

        if event_type == "user.deleted":
            data = _require_event_data(data, event_type=event_type)
            clerk_id = _require_deleted_user_id(data)
            await self._repository.soft_delete_by_clerk_id(
                session,
                clerk_id=clerk_id,
                deleted_at=datetime.now(UTC),
            )
            return


def _require_event_data(data: object, *, event_type: object) -> dict[str, Any]:
    if isinstance(data, dict):
        return data
    raise ApiError(
        code="invalid_webhook_payload",
        message=f"Clerk {event_type} webhook payload is missing an object data field.",
        status_code=status.HTTP_400_BAD_REQUEST,
    )


def _require_deleted_user_id(data: dict[str, Any]) -> str:
    clerk_id = data.get("id")
    if isinstance(clerk_id, str) and clerk_id.strip():
        return clerk_id.strip()
    raise ApiError(
        code="invalid_webhook_payload",
        message="Clerk user.deleted webhook payload is missing a user id.",
        status_code=status.HTTP_400_BAD_REQUEST,
    )
