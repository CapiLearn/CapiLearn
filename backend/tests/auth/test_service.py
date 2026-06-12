from datetime import UTC, datetime
from inspect import signature
from uuid import uuid4

import pytest
from fastapi import status
from sqlalchemy.exc import IntegrityError

from backend.auth.models import UserAccount
from backend.auth.repository import UserAccountRepository
from backend.auth.schemas import AuthPrincipal, ClerkAuthClaims, UserRole
from backend.auth.service import AuthTestModeService, AuthUserService
from backend.core.exceptions import ApiError


@pytest.mark.asyncio
async def test_missing_local_user_creates_student_user() -> None:
    session = FakeSession()
    repository = FakeUserRepository()

    current_user = await AuthUserService(repository).get_or_create_current_user(
        session,
        ClerkAuthClaims(
            clerk_id="user_new",
            email="new@example.com",
            display_name="New User",
            claims={"sub": "user_new"},
        ),
    )

    assert current_user.clerk_id == "user_new"
    assert current_user.email == "new@example.com"
    assert current_user.display_name == "New User"
    assert current_user.role == UserRole.STUDENT
    assert session.commits == 1
    assert session.rollbacks == 0
    assert repository.calls == [
        ("get_by_clerk_id", "user_new"),
        ("create", "user_new", UserRole.STUDENT),
    ]
    assert repository.user is not None
    assert not hasattr(repository.user, "email")
    assert not hasattr(repository.user, "display_name")


@pytest.mark.asyncio
async def test_existing_local_user_is_loaded_by_clerk_id() -> None:
    user_id = uuid4()
    user = UserAccount(id=user_id, clerk_id="user_existing", role=UserRole.ADMIN.value)
    session = FakeSession()
    repository = FakeUserRepository(user=user)

    current_user = await AuthUserService(repository).get_or_create_current_user(
        session,
        ClerkAuthClaims(clerk_id="user_existing", claims={"sub": "user_existing"}),
    )

    assert current_user.id == user_id
    assert current_user.email is None
    assert current_user.display_name is None
    assert current_user.role == UserRole.ADMIN
    assert session.commits == 0
    assert repository.calls == [("get_by_clerk_id", "user_existing")]


@pytest.mark.asyncio
async def test_existing_local_user_returns_request_profile_claims_without_commit() -> None:
    user = UserAccount(
        id=uuid4(),
        clerk_id="user_existing",
        role=UserRole.STUDENT.value,
    )
    session = FakeSession()
    repository = FakeUserRepository(user=user)

    current_user = await AuthUserService(repository).get_or_create_current_user(
        session,
        ClerkAuthClaims(
            clerk_id="user_existing",
            email="new@example.com",
            display_name="New Name",
            claims={"sub": "user_existing"},
        ),
    )

    assert current_user.email == "new@example.com"
    assert current_user.display_name == "New Name"
    assert not hasattr(user, "email")
    assert not hasattr(user, "display_name")
    assert session.commits == 0
    assert repository.calls == [("get_by_clerk_id", "user_existing")]


@pytest.mark.asyncio
async def test_auth_claim_role_payload_does_not_seed_local_role() -> None:
    session = FakeSession()
    repository = FakeUserRepository()

    current_user = await AuthUserService(repository).get_or_create_current_user(
        session,
        ClerkAuthClaims(
            clerk_id="user_role_claim",
            claims={"sub": "user_role_claim", "role": "admin"},
        ),
    )

    assert current_user.role == UserRole.STUDENT
    assert repository.user is not None
    assert repository.user.role == UserRole.STUDENT.value
    assert session.commits == 1
    assert repository.calls == [
        ("get_by_clerk_id", "user_role_claim"),
        ("create", "user_role_claim", UserRole.STUDENT),
    ]


@pytest.mark.asyncio
async def test_auth_claim_role_payload_does_not_override_existing_local_role() -> None:
    user = UserAccount(
        id=uuid4(),
        clerk_id="user_role_claim",
        role=UserRole.STUDENT.value,
    )
    session = FakeSession()
    repository = FakeUserRepository(user=user)

    current_user = await AuthUserService(repository).get_or_create_current_user(
        session,
        ClerkAuthClaims(
            clerk_id="user_role_claim",
            claims={"sub": "user_role_claim", "role": "admin"},
        ),
    )

    assert current_user.role == UserRole.STUDENT
    assert user.role == UserRole.STUDENT.value
    assert session.commits == 0
    assert repository.calls == [("get_by_clerk_id", "user_role_claim")]


@pytest.mark.asyncio
async def test_explicit_initial_role_seeds_new_local_user() -> None:
    session = FakeSession()
    repository = FakeUserRepository()

    current_user = await AuthUserService(repository).get_or_create_current_user(
        session,
        ClerkAuthClaims(
            clerk_id="user_test_admin",
            claims={"sub": "user_test_admin"},
        ),
        initial_role=UserRole.ADMIN,
    )

    assert current_user.role == UserRole.ADMIN
    assert repository.user is not None
    assert repository.user.role == UserRole.ADMIN.value
    assert session.commits == 1
    assert repository.calls == [
        ("get_by_clerk_id", "user_test_admin"),
        ("create", "user_test_admin", UserRole.ADMIN),
    ]


@pytest.mark.asyncio
async def test_existing_current_user_returns_none_for_missing_local_user() -> None:
    session = FakeSession()
    repository = FakeUserRepository()

    current_user = await AuthUserService(repository).get_existing_current_user(
        session,
        ClerkAuthClaims(clerk_id="user_missing", claims={"sub": "user_missing"}),
    )

    assert current_user is None
    assert session.commits == 0
    assert repository.calls == [("get_by_clerk_id", "user_missing")]


@pytest.mark.asyncio
async def test_existing_current_user_loads_without_profile_mutation() -> None:
    user = UserAccount(
        id=uuid4(),
        clerk_id="user_existing",
        role=UserRole.STUDENT.value,
    )
    session = FakeSession()
    repository = FakeUserRepository(user=user)

    current_user = await AuthUserService(repository).get_existing_current_user(
        session,
        ClerkAuthClaims(
            clerk_id="user_existing",
            email="new@example.com",
            display_name="New Name",
            claims={"sub": "user_existing"},
        ),
    )

    assert current_user is not None
    assert current_user.id == user.id
    assert current_user.email == "new@example.com"
    assert current_user.display_name == "New Name"
    assert not hasattr(user, "email")
    assert not hasattr(user, "display_name")
    assert session.commits == 0
    assert repository.calls == [("get_by_clerk_id", "user_existing")]


@pytest.mark.asyncio
async def test_soft_deleted_user_is_rejected() -> None:
    user = UserAccount(
        id=uuid4(),
        clerk_id="user_deleted",
        role=UserRole.STUDENT.value,
        deleted_at=datetime.now(UTC),
    )
    session = FakeSession()
    repository = FakeUserRepository(user=user)

    with pytest.raises(ApiError) as exc_info:
        await AuthUserService(repository).get_or_create_current_user(
            session,
            ClerkAuthClaims(clerk_id="user_deleted", claims={"sub": "user_deleted"}),
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.code == "forbidden"
    assert session.commits == 0


@pytest.mark.asyncio
async def test_claim_updates_do_not_mutate_soft_deleted_user() -> None:
    user = UserAccount(
        id=uuid4(),
        clerk_id="user_deleted",
        role=UserRole.STUDENT.value,
        deleted_at=datetime.now(UTC),
    )
    session = FakeSession()
    repository = FakeUserRepository(user=user)

    with pytest.raises(ApiError) as exc_info:
        await AuthUserService(repository).get_or_create_current_user(
            session,
            ClerkAuthClaims(
                clerk_id="user_deleted",
                email="new@example.com",
                display_name="New Name",
                claims={"sub": "user_deleted"},
            ),
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.code == "forbidden"
    assert not hasattr(user, "email")
    assert not hasattr(user, "display_name")
    assert user.role == UserRole.STUDENT.value
    assert session.commits == 0
    assert repository.calls == [("get_by_clerk_id", "user_deleted")]


@pytest.mark.asyncio
async def test_existing_current_user_rejects_soft_deleted_user() -> None:
    user = UserAccount(
        id=uuid4(),
        clerk_id="user_deleted",
        role=UserRole.STUDENT.value,
        deleted_at=datetime.now(UTC),
    )
    session = FakeSession()
    repository = FakeUserRepository(user=user)

    with pytest.raises(ApiError) as exc_info:
        await AuthUserService(repository).get_existing_current_user(
            session,
            ClerkAuthClaims(clerk_id="user_deleted", claims={"sub": "user_deleted"}),
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.code == "forbidden"
    assert session.commits == 0
    assert repository.calls == [("get_by_clerk_id", "user_deleted")]


@pytest.mark.asyncio
async def test_concurrent_first_request_conflict_rolls_back_and_returns_existing_user() -> None:
    existing_user = UserAccount(
        id=uuid4(),
        clerk_id="user_race",
        role=UserRole.STUDENT.value,
    )
    session = FakeSession()
    repository = FakeUserRepository(
        lookup_results=[None, existing_user],
        create_error=_integrity_error(),
    )

    current_user = await AuthUserService(repository).get_or_create_current_user(
        session,
        ClerkAuthClaims(clerk_id="user_race", claims={"sub": "user_race"}),
    )

    assert current_user.id == existing_user.id
    assert session.rollbacks == 1
    assert session.commits == 0
    assert repository.calls == [
        ("get_by_clerk_id", "user_race"),
        ("create", "user_race", UserRole.STUDENT),
        ("get_by_clerk_id", "user_race"),
    ]


@pytest.mark.asyncio
async def test_conflict_without_existing_user_reraises_original_integrity_error() -> None:
    session = FakeSession()
    integrity_error = _integrity_error()
    repository = FakeUserRepository(
        lookup_results=[None, None],
        create_error=integrity_error,
    )

    with pytest.raises(IntegrityError) as exc_info:
        await AuthUserService(repository).get_or_create_current_user(
            session,
            ClerkAuthClaims(clerk_id="user_missing", claims={"sub": "user_missing"}),
        )

    assert exc_info.value is integrity_error
    assert session.rollbacks == 1
    assert session.commits == 0


def _integrity_error() -> IntegrityError:
    return IntegrityError("insert user", {}, Exception("duplicate clerk_id"))


def test_get_or_create_current_user_has_no_role_override_parameter() -> None:
    parameters = signature(AuthUserService.get_or_create_current_user).parameters

    assert "role_override" not in parameters


@pytest.mark.asyncio
async def test_test_auth_current_user_overrides_role_without_mutating_existing_user() -> None:
    user = UserAccount(
        id=uuid4(),
        clerk_id="user_test_admin",
        role=UserRole.STUDENT.value,
    )
    session = FakeSession()
    repository = FakeUserRepository(user=user)

    current_user = await AuthTestModeService(
        repository,
        role=UserRole.ADMIN,
    ).get_or_create_current_user(
        session,
        ClerkAuthClaims(
            clerk_id="user_test_admin",
            email="admin@example.com",
            display_name="Test Admin",
            claims={"sub": "user_test_admin"},
        ),
    )

    assert current_user.id == user.id
    assert current_user.clerk_id == "user_test_admin"
    assert current_user.email == "admin@example.com"
    assert current_user.display_name == "Test Admin"
    assert current_user.role == UserRole.ADMIN
    assert user.role == UserRole.STUDENT.value
    assert session.commits == 0
    assert repository.calls == [("get_by_clerk_id", "user_test_admin")]


@pytest.mark.asyncio
async def test_test_auth_principal_for_missing_user_is_not_db_backed_current_user() -> None:
    session = FakeSession()
    repository = FakeUserRepository()

    principal = await AuthTestModeService(
        repository,
        role=UserRole.ADMIN,
    ).get_current_principal(
        session,
        ClerkAuthClaims(
            clerk_id="user_test_admin",
            email="admin@example.com",
            display_name="Test Admin",
            claims={"sub": "user_test_admin"},
        ),
    )

    assert isinstance(principal, AuthPrincipal)
    assert not hasattr(principal, "id")
    assert principal.clerk_id == "user_test_admin"
    assert principal.email == "admin@example.com"
    assert principal.display_name == "Test Admin"
    assert principal.role == UserRole.ADMIN
    assert repository.user is None
    assert session.commits == 0
    assert repository.calls == [("get_by_clerk_id", "user_test_admin")]


@pytest.mark.asyncio
async def test_test_auth_principal_propagates_disabled_user_error() -> None:
    user = UserAccount(
        id=uuid4(),
        clerk_id="user_disabled",
        role=UserRole.ADMIN.value,
        deleted_at=datetime.now(UTC),
    )
    session = FakeSession()
    repository = FakeUserRepository(user=user)

    with pytest.raises(ApiError) as exc_info:
        await AuthTestModeService(
            repository,
            role=UserRole.ADMIN,
        ).get_current_principal(
            session,
            ClerkAuthClaims(clerk_id="user_disabled", claims={"sub": "user_disabled"}),
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.code == "forbidden"
    assert session.commits == 0
    assert repository.calls == [("get_by_clerk_id", "user_disabled")]


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


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

    async def get_by_clerk_id(self, session, *, clerk_id: str) -> UserAccount | None:
        self.calls.append(("get_by_clerk_id", clerk_id))
        if self.lookup_results:
            return self.lookup_results.pop(0)
        return self.user

    async def create(
        self,
        session,
        *,
        clerk_id: str,
        role: UserRole = UserRole.STUDENT,
    ) -> UserAccount:
        self.calls.append(("create", clerk_id, role))
        if self.create_error is not None:
            raise self.create_error
        self.user = UserAccount(
            id=uuid4(),
            clerk_id=clerk_id,
            role=role.value,
        )
        return self.user
