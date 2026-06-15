from datetime import datetime
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from backend.auth.models import UserAccount
from backend.auth.repository import UserAccountRepository
from backend.auth.schemas import UserRole


class FakeUserRepository(UserAccountRepository):
    def __init__(
        self,
        user: UserAccount | None = None,
        *,
        lookup_results: list[UserAccount | None] | None = None,
        create_error: IntegrityError | None = None,
    ) -> None:
        self.user = user
        self.lookup_results = lookup_results or []
        self.create_error = create_error
        self.calls = []
        self.profile_update_calls = []

    async def get_by_clerk_id(self, session, *, clerk_id: str) -> UserAccount | None:
        self.calls.append(("get_by_clerk_id", clerk_id))
        if self.lookup_results:
            user = self.lookup_results.pop(0)
            if user is not None and user.clerk_id != clerk_id:
                raise AssertionError(
                    "FakeUserRepository queued lookup user clerk_id "
                    f"{user.clerk_id!r} does not match lookup clerk_id {clerk_id!r}"
                )
            return user
        if self.user is None:
            return None
        if self.user.clerk_id != clerk_id:
            raise AssertionError(
                "FakeUserRepository stored user clerk_id "
                f"{self.user.clerk_id!r} does not match lookup clerk_id {clerk_id!r}"
            )
        return self.user

    async def create(
        self,
        session,
        *,
        clerk_id: str,
        role: UserRole = UserRole.STUDENT,
        display_name: str,
        email: str | None = None,
        profile_synced_at: datetime,
    ) -> UserAccount:
        self.calls.append(("create", clerk_id, role))
        if self.create_error is not None:
            raise self.create_error
        self.user = UserAccount(
            id=uuid4(),
            clerk_id=clerk_id,
            role=role.value,
            display_name=display_name,
            email=email,
            profile_synced_at=profile_synced_at,
        )
        return self.user

    async def update_profile_projection(
        self,
        session,
        *,
        user: UserAccount,
        display_name: str,
        email: str | None,
        synced_at: datetime,
    ) -> bool:
        self.profile_update_calls.append((user, display_name, email, synced_at))
        return await super().update_profile_projection(
            session,
            user=user,
            display_name=display_name,
            email=email,
            synced_at=synced_at,
        )

    async def upsert_from_clerk_profile(
        self,
        session,
        *,
        clerk_id: str,
        display_name: str,
        email: str | None,
        clerk_profile_updated_at: datetime,
        synced_at: datetime,
        default_role: UserRole = UserRole.STUDENT,
    ) -> UserAccount:
        self.calls.append(
            (
                "upsert_from_clerk_profile",
                clerk_id,
                display_name,
                email,
                clerk_profile_updated_at,
                synced_at,
                default_role,
            )
        )
        if self.user is None:
            self.user = UserAccount(
                id=uuid4(),
                clerk_id=clerk_id,
                role=default_role.value,
                display_name=display_name,
                email=email,
                profile_synced_at=synced_at,
                clerk_profile_updated_at=clerk_profile_updated_at,
            )
            return self.user

        if self.user.clerk_id != clerk_id:
            raise AssertionError(
                "FakeUserRepository stored user clerk_id "
                f"{self.user.clerk_id!r} does not match upsert clerk_id {clerk_id!r}"
            )
        self.user.display_name = display_name
        self.user.email = email
        self.user.profile_synced_at = synced_at
        self.user.clerk_profile_updated_at = clerk_profile_updated_at
        return self.user

    async def soft_delete_by_clerk_id(
        self,
        session,
        *,
        clerk_id: str,
        deleted_at: datetime,
    ) -> bool:
        self.calls.append(("soft_delete_by_clerk_id", clerk_id))
        if self.user is None or self.user.clerk_id != clerk_id or self.user.deleted_at is not None:
            return False
        self.user.deleted_at = deleted_at
        return True
