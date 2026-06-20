from datetime import UTC, datetime
from inspect import signature
from uuid import uuid4

import pytest
from fastapi import status
from sqlalchemy.exc import IntegrityError

from backend.auth.models import UserAccount
from backend.auth.schemas import ClerkAuthClaims, UserRole
from backend.auth.service import AuthTestModeService, AuthUserService
from backend.core.exceptions import ApiError
from backend.tests.fakes import FakeUserRepository


@pytest.mark.asyncio
async def test_missing_local_user_creates_student_user_from_complete_claims() -> None:
    session = FakeSession()
    repository = FakeUserRepository()

    current_user = await AuthUserService(repository).get_or_create_current_user(
        session,
        _claims("user_new", first_name="New", last_name="User"),
    )

    assert current_user.clerk_id == "user_new"
    assert current_user.display_name == "New User"
    assert current_user.role == UserRole.STUDENT
    assert session.commits == 1
    assert session.rollbacks == 0
    assert repository.calls == [
        ("get_by_clerk_id", "user_new"),
        ("create", "user_new", UserRole.STUDENT),
    ]
    assert repository.user is not None
    assert repository.user.first_name == "New"
    assert repository.user.last_name == "User"


@pytest.mark.asyncio
async def test_existing_local_user_repairs_changed_claim_names_before_webhook_sync() -> None:
    user = _user(clerk_id="user_existing", first_name="Old", last_name="Name")
    session = FakeSession()
    repository = FakeUserRepository(user=user)

    current_user = await AuthUserService(repository).get_or_create_current_user(
        session,
        _claims("user_existing", first_name="New", last_name="Name"),
    )

    assert current_user.id == user.id
    assert current_user.display_name == "New Name"
    assert user.first_name == "New"
    assert user.last_name == "Name"
    assert session.commits == 1
    assert repository.calls == [("get_by_clerk_id", "user_existing")]
    assert repository.profile_update_calls == [(user, "New", "Name")]


@pytest.mark.asyncio
async def test_existing_local_user_skips_unchanged_claim_names() -> None:
    user = _user(clerk_id="user_existing", first_name="Same", last_name="Name")
    session = FakeSession()
    repository = FakeUserRepository(user=user)

    current_user = await AuthUserService(repository).get_or_create_current_user(
        session,
        _claims("user_existing", first_name="Same", last_name="Name"),
    )

    assert current_user.display_name == "Same Name"
    assert session.commits == 0
    assert repository.profile_update_calls == [(user, "Same", "Name")]


@pytest.mark.asyncio
async def test_auth_claim_role_payload_does_not_seed_local_role() -> None:
    session = FakeSession()
    repository = FakeUserRepository()

    current_user = await AuthUserService(repository).get_or_create_current_user(
        session,
        _claims(
            "user_role_claim",
            claims={
                "sub": "user_role_claim",
                "first_name": "Test",
                "last_name": "User",
                "role": "admin",
            },
        ),
    )

    assert current_user.role == UserRole.STUDENT
    assert repository.user is not None
    assert repository.user.role == UserRole.STUDENT.value
    assert session.commits == 1


@pytest.mark.asyncio
async def test_auth_claim_role_payload_does_not_override_existing_local_role() -> None:
    user = _user(clerk_id="user_role_claim", role=UserRole.STUDENT)
    session = FakeSession()
    repository = FakeUserRepository(user=user)

    current_user = await AuthUserService(repository).get_or_create_current_user(
        session,
        _claims(
            "user_role_claim",
            claims={
                "sub": "user_role_claim",
                "first_name": "Test",
                "last_name": "User",
                "role": "admin",
            },
        ),
    )

    assert current_user.role == UserRole.STUDENT
    assert user.role == UserRole.STUDENT.value
    assert session.commits == 0


@pytest.mark.asyncio
async def test_explicit_initial_role_seeds_new_local_user() -> None:
    session = FakeSession()
    repository = FakeUserRepository()

    current_user = await AuthUserService(repository).get_or_create_current_user(
        session,
        _claims("user_test_admin", first_name="Test", last_name="Admin"),
        initial_role=UserRole.ADMIN,
    )

    assert current_user.role == UserRole.ADMIN
    assert repository.user is not None
    assert repository.user.role == UserRole.ADMIN.value
    assert session.commits == 1


@pytest.mark.asyncio
async def test_existing_current_user_returns_none_for_missing_local_user() -> None:
    session = FakeSession()
    repository = FakeUserRepository()

    current_user = await AuthUserService(repository).get_existing_current_user(
        session,
        _claims("user_missing"),
    )

    assert current_user is None
    assert session.commits == 0
    assert repository.calls == [("get_by_clerk_id", "user_missing")]


@pytest.mark.asyncio
async def test_existing_current_user_reads_stored_names_without_syncing_claims() -> None:
    user = _user(clerk_id="user_existing", first_name="Old", last_name="Name")
    session = FakeSession()
    repository = FakeUserRepository(user=user)

    current_user = await AuthUserService(repository).get_existing_current_user(
        session,
        _claims("user_existing", first_name="New", last_name="Name"),
    )

    assert current_user is not None
    assert current_user.id == user.id
    assert current_user.display_name == "Old Name"
    assert user.first_name == "Old"
    assert user.last_name == "Name"
    assert session.commits == 0
    assert repository.profile_update_calls == []


@pytest.mark.asyncio
async def test_existing_current_user_accepts_subject_only_claims_without_profile_sync() -> None:
    user = _user(clerk_id="user_subject_only", first_name="Stored", last_name="User")
    session = FakeSession()
    repository = FakeUserRepository(user=user)

    current_user = await AuthUserService(repository).get_existing_current_user(
        session,
        ClerkAuthClaims(
            clerk_id="user_subject_only",
            claims={"sub": "user_subject_only"},
        ),
    )

    assert current_user is not None
    assert current_user.id == user.id
    assert current_user.display_name == "Stored User"
    assert session.commits == 0
    assert repository.profile_update_calls == []


@pytest.mark.asyncio
async def test_existing_current_user_rejects_invalid_persisted_role() -> None:
    user = UserAccount(
        id=uuid4(),
        clerk_id="user_invalid_role",
        first_name="Invalid",
        last_name="Role",
        role="owner",
    )
    session = FakeSession()
    repository = FakeUserRepository(user=user)

    with pytest.raises(ApiError) as exc_info:
        await AuthUserService(repository).get_existing_current_user(
            session,
            ClerkAuthClaims(
                clerk_id="user_invalid_role",
                claims={"sub": "user_invalid_role"},
            ),
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.code == "forbidden"
    assert session.commits == 0
    assert repository.calls == [("get_by_clerk_id", "user_invalid_role")]


@pytest.mark.asyncio
async def test_current_principal_uses_role_without_profile_claims_or_sync() -> None:
    user = _user(clerk_id="user_existing", role=UserRole.ADMIN)
    session = FakeSession()
    repository = FakeUserRepository(user=user)

    principal = await AuthUserService(repository).get_current_principal(
        session,
        ClerkAuthClaims(
            clerk_id="user_existing",
            claims={"sub": "user_existing"},
        ),
    )

    assert principal is not None
    assert principal.clerk_id == "user_existing"
    assert principal.role == UserRole.ADMIN
    assert session.commits == 0
    assert repository.profile_update_calls == []


@pytest.mark.asyncio
async def test_claim_updates_do_not_mutate_soft_deleted_user() -> None:
    user = _user(clerk_id="user_deleted", deleted_at=datetime.now(UTC))
    session = FakeSession()
    repository = FakeUserRepository(user=user)

    with pytest.raises(ApiError) as exc_info:
        await AuthUserService(repository).get_or_create_current_user(
            session,
            _claims("user_deleted", first_name="New", last_name="Name"),
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.code == "forbidden"
    assert user.first_name == "Test"
    assert user.last_name == "User"
    assert session.commits == 0
    assert repository.profile_update_calls == []


@pytest.mark.asyncio
async def test_existing_current_user_rejects_soft_deleted_user() -> None:
    user = _user(clerk_id="user_deleted", deleted_at=datetime.now(UTC))
    session = FakeSession()
    repository = FakeUserRepository(user=user)

    with pytest.raises(ApiError) as exc_info:
        await AuthUserService(repository).get_existing_current_user(
            session,
            _claims("user_deleted"),
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.code == "forbidden"
    assert session.commits == 0


@pytest.mark.asyncio
async def test_concurrent_first_request_conflict_repairs_existing_user_profile() -> None:
    existing_user = _user(clerk_id="user_race", first_name="Old", last_name="Race")
    session = FakeSession()
    repository = FakeUserRepository(
        lookup_results=[None, existing_user],
        create_error=_integrity_error(),
    )

    current_user = await AuthUserService(repository).get_or_create_current_user(
        session,
        _claims("user_race", first_name="Race", last_name="User"),
    )

    assert current_user.id == existing_user.id
    assert current_user.display_name == "Race User"
    assert existing_user.first_name == "Race"
    assert existing_user.last_name == "User"
    assert session.rollbacks == 1
    assert session.commits == 1
    assert repository.calls == [
        ("get_by_clerk_id", "user_race"),
        ("create", "user_race", UserRole.STUDENT),
        ("get_by_clerk_id", "user_race"),
    ]
    assert repository.profile_update_calls == [(existing_user, "Race", "User")]


@pytest.mark.asyncio
async def test_concurrent_first_request_conflict_skips_unchanged_profile() -> None:
    existing_user = _user(clerk_id="user_race", first_name="Race", last_name="User")
    session = FakeSession()
    repository = FakeUserRepository(
        lookup_results=[None, existing_user],
        create_error=_integrity_error(),
    )

    current_user = await AuthUserService(repository).get_or_create_current_user(
        session,
        _claims("user_race", first_name="Race", last_name="User"),
    )

    assert current_user.id == existing_user.id
    assert current_user.display_name == "Race User"
    assert session.rollbacks == 1
    assert session.commits == 0
    assert repository.calls == [
        ("get_by_clerk_id", "user_race"),
        ("create", "user_race", UserRole.STUDENT),
        ("get_by_clerk_id", "user_race"),
    ]


@pytest.mark.asyncio
async def test_session_claim_repair_does_not_override_webhook_synced_profile() -> None:
    user = _user(
        clerk_id="user_existing",
        first_name="Webhook",
        last_name="Name",
        clerk_profile_updated_at=datetime(2026, 6, 14, tzinfo=UTC),
    )
    session = FakeSession()
    repository = FakeUserRepository(user=user)

    current_user = await AuthUserService(repository).get_or_create_current_user(
        session,
        _claims("user_existing", first_name="Claim", last_name="Name"),
    )

    assert current_user.display_name == "Webhook Name"
    assert user.first_name == "Webhook"
    assert user.last_name == "Name"
    assert session.commits == 0
    assert repository.profile_update_calls == []


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
            _claims("user_missing"),
        )

    assert exc_info.value is integrity_error
    assert session.rollbacks == 1
    assert session.commits == 0


def test_get_or_create_current_user_has_no_role_override_parameter() -> None:
    parameters = signature(AuthUserService.get_or_create_current_user).parameters

    assert "role_override" not in parameters


@pytest.mark.asyncio
async def test_test_auth_current_user_overrides_role_without_mutating_local_role() -> None:
    user = _user(clerk_id="user_test_admin", first_name="Test", last_name="Admin")
    session = FakeSession()
    repository = FakeUserRepository(user=user)

    current_user = await AuthTestModeService(
        repository,
        role=UserRole.ADMIN,
    ).get_or_create_current_user(
        session,
        _claims("user_test_admin", first_name="Test", last_name="Admin"),
    )

    assert current_user.id == user.id
    assert current_user.clerk_id == "user_test_admin"
    assert current_user.display_name == "Test Admin"
    assert current_user.role == UserRole.ADMIN
    assert user.role == UserRole.STUDENT.value
    assert session.commits == 0


@pytest.mark.asyncio
async def test_test_auth_principal_for_missing_user_returns_none() -> None:
    session = FakeSession()
    repository = FakeUserRepository()

    principal = await AuthTestModeService(
        repository,
        role=UserRole.ADMIN,
    ).get_current_principal(
        session,
        _claims("user_test_admin", first_name="Test", last_name="Admin"),
    )

    assert principal is None
    assert repository.user is None
    assert session.commits == 0


@pytest.mark.asyncio
async def test_test_auth_principal_overrides_role_without_syncing_existing_user() -> None:
    user = _user(clerk_id="user_test_admin", first_name="Stored", last_name="Admin")
    session = FakeSession()
    repository = FakeUserRepository(user=user)

    principal = await AuthTestModeService(
        repository,
        role=UserRole.ADMIN,
    ).get_current_principal(
        session,
        _claims("user_test_admin", first_name="Claim", last_name="Admin"),
    )

    assert principal is not None
    assert principal.clerk_id == "user_test_admin"
    assert principal.role == UserRole.ADMIN
    assert user.first_name == "Stored"
    assert user.last_name == "Admin"
    assert session.commits == 0
    assert repository.profile_update_calls == []


@pytest.mark.asyncio
async def test_test_auth_principal_propagates_disabled_user_error() -> None:
    user = _user(clerk_id="user_disabled", role=UserRole.ADMIN, deleted_at=datetime.now(UTC))
    session = FakeSession()
    repository = FakeUserRepository(user=user)

    with pytest.raises(ApiError) as exc_info:
        await AuthTestModeService(
            repository,
            role=UserRole.ADMIN,
        ).get_current_principal(
            session,
            _claims("user_disabled"),
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.code == "forbidden"
    assert session.commits == 0


def _claims(
    clerk_id: str,
    *,
    first_name: str = "Test",
    last_name: str = "User",
    claims: dict | None = None,
) -> ClerkAuthClaims:
    payload = {
        "sub": clerk_id,
        "first_name": first_name,
        "last_name": last_name,
    }
    if claims is not None:
        payload.update(claims)
    return ClerkAuthClaims(
        clerk_id=clerk_id,
        claims=payload,
    )


def _user(
    *,
    clerk_id: str,
    first_name: str = "Test",
    last_name: str = "User",
    role: UserRole = UserRole.STUDENT,
    deleted_at: datetime | None = None,
    clerk_profile_updated_at: datetime | None = None,
) -> UserAccount:
    return UserAccount(
        id=uuid4(),
        clerk_id=clerk_id,
        first_name=first_name,
        last_name=last_name,
        clerk_profile_updated_at=clerk_profile_updated_at,
        role=role.value,
        deleted_at=deleted_at,
    )


def _integrity_error() -> IntegrityError:
    return IntegrityError("insert user", {}, Exception("duplicate clerk_id"))


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.flushes = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def flush(self) -> None:
        self.flushes += 1
