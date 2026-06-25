import base64
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient
from svix.webhooks import Webhook

from backend.auth.clerk_webhook_service import ClerkWebhookService
from backend.core.config import Settings, get_settings
from backend.core.database import get_db
from backend.main import app
from backend.webhooks.router import get_clerk_webhook_service

WEBHOOK_SECRET = "whsec_" + base64.b64encode(b"capilearn-test-secret").decode()


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_clerk_webhook_handles_user_created() -> None:
    session = FakeSession()
    service = CapturingWebhookService()
    app.dependency_overrides[get_settings] = lambda: Settings(
        clerk_webhook_signing_secret=WEBHOOK_SECRET,
    )
    app.dependency_overrides[get_db] = _fake_db_override(session)
    app.dependency_overrides[get_clerk_webhook_service] = lambda: service

    event = _user_event("user.created")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/webhooks/clerk",
            content=_event_body(event),
            headers=_svix_headers(event),
        )

    assert response.status_code == 204
    assert service.events == [event]
    assert session.commits == 1


@pytest.mark.asyncio
async def test_clerk_webhook_returns_204_for_unsupported_verified_event() -> None:
    session = FakeSession()
    service = CapturingWebhookService()
    app.dependency_overrides[get_settings] = lambda: Settings(
        clerk_webhook_signing_secret=WEBHOOK_SECRET,
    )
    app.dependency_overrides[get_db] = _fake_db_override(session)
    app.dependency_overrides[get_clerk_webhook_service] = lambda: service

    event = {"type": "session.created", "data": {"id": "sess_123"}}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/webhooks/clerk",
            content=_event_body(event),
            headers=_svix_headers(event),
        )

    assert response.status_code == 204
    assert service.events == [event]
    assert session.commits == 1


@pytest.mark.asyncio
async def test_clerk_webhook_rejects_invalid_signature() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        clerk_webhook_signing_secret=WEBHOOK_SECRET,
    )
    app.dependency_overrides[get_db] = _fake_db_override(FakeSession())

    event = _user_event("user.updated")
    headers = _svix_headers(event)
    headers["svix-signature"] = "v1,invalid"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/webhooks/clerk",
            content=_event_body(event),
            headers=headers,
        )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_webhook_signature"


@pytest.mark.asyncio
async def test_clerk_webhook_reports_missing_signing_secret_as_server_misconfiguration() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(clerk_webhook_signing_secret=None)
    app.dependency_overrides[get_db] = _fake_db_override(FakeSession())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/webhooks/clerk", content=b"{}")

    assert response.status_code == 500
    assert response.json()["code"] == "webhook_not_configured"


@pytest.mark.asyncio
async def test_clerk_webhook_rejects_supported_update_with_invalid_data_without_commit() -> None:
    session = FakeSession()
    app.dependency_overrides[get_settings] = lambda: Settings(
        clerk_webhook_signing_secret=WEBHOOK_SECRET,
    )
    app.dependency_overrides[get_db] = _fake_db_override(session)
    app.dependency_overrides[get_clerk_webhook_service] = lambda: ClerkWebhookService(
        repository=CapturingRepository()
    )

    event = {"type": "user.updated", "data": None}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/webhooks/clerk",
            content=_event_body(event),
            headers=_svix_headers(event),
        )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["code"] == "invalid_webhook_payload"
    assert session.commits == 0


@pytest.mark.asyncio
async def test_clerk_webhook_rejects_supported_create_with_invalid_profile_without_commit() -> None:
    session = FakeSession()
    app.dependency_overrides[get_settings] = lambda: Settings(
        clerk_webhook_signing_secret=WEBHOOK_SECRET,
    )
    app.dependency_overrides[get_db] = _fake_db_override(session)
    app.dependency_overrides[get_clerk_webhook_service] = lambda: ClerkWebhookService(
        repository=CapturingRepository()
    )

    event = _user_event("user.created")
    del event["data"]["first_name"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/webhooks/clerk",
            content=_event_body(event),
            headers=_svix_headers(event),
        )

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["code"] == "profile_incomplete"
    assert session.commits == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("data", [{}, {"id": "  "}])
async def test_clerk_webhook_rejects_delete_without_user_id_without_commit(
    data: dict[str, object],
) -> None:
    session = FakeSession()
    app.dependency_overrides[get_settings] = lambda: Settings(
        clerk_webhook_signing_secret=WEBHOOK_SECRET,
    )
    app.dependency_overrides[get_db] = _fake_db_override(session)
    app.dependency_overrides[get_clerk_webhook_service] = lambda: ClerkWebhookService(
        repository=CapturingRepository()
    )

    event = {"type": "user.deleted", "data": data}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/webhooks/clerk",
            content=_event_body(event),
            headers=_svix_headers(event),
        )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["code"] == "invalid_webhook_payload"
    assert session.commits == 0


@pytest.mark.asyncio
async def test_clerk_webhook_service_dispatches_profile_upsert_and_soft_delete() -> None:
    repository = CapturingRepository()
    service = ClerkWebhookService(repository=repository)
    session = object()

    await service.handle_event(session, _user_event("user.updated"))
    await service.handle_event(session, {"type": "user.deleted", "data": {"id": "user_123"}})

    assert repository.upserts[0][0] is session
    assert repository.upserts[0][1] == {
        "clerk_id": "user_123",
        "first_name": "Jane",
        "last_name": "Doe",
        "clerk_profile_updated_at": datetime(2026, 6, 15, 16, 0, tzinfo=UTC),
    }
    assert repository.deletes[0][0] is session
    assert repository.deletes[0][1] == "user_123"


def _user_event(event_type: str) -> dict:
    return {
        "type": event_type,
        "data": {
            "id": "user_123",
            "first_name": "Jane",
            "last_name": "Doe",
            "primary_email_address_id": "email_123",
            "email_addresses": [
                {
                    "id": "email_123",
                    "email_address": "jane@example.com",
                }
            ],
            "updated_at": 1781539200000,
        },
    }


def _event_body(event: dict) -> bytes:
    return json.dumps(event, separators=(",", ":")).encode()


def _svix_headers(event: dict) -> dict[str, str]:
    body = _event_body(event).decode()
    msg_id = f"msg_{uuid4().hex}"
    timestamp = datetime.now(UTC)
    signature = Webhook(WEBHOOK_SECRET).sign(msg_id, timestamp, body)
    return {
        "content-type": "application/json",
        "svix-id": msg_id,
        "svix-timestamp": str(int(timestamp.timestamp())),
        "svix-signature": signature,
    }


def _fake_db_override(session):
    async def override():
        yield session

    return override


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class CapturingWebhookService:
    def __init__(self) -> None:
        self.events = []

    async def handle_event(self, session, event: dict) -> None:
        self.events.append(event)


class CapturingRepository:
    def __init__(self) -> None:
        self.upserts = []
        self.deletes = []

    async def upsert_from_clerk_profile(
        self,
        session,
        *,
        clerk_id,
        first_name,
        last_name,
        clerk_profile_updated_at,
    ):
        self.upserts.append(
            (
                session,
                {
                    "clerk_id": clerk_id,
                    "first_name": first_name,
                    "last_name": last_name,
                    "clerk_profile_updated_at": clerk_profile_updated_at,
                },
            )
        )

    async def soft_delete_by_clerk_id(self, session, *, clerk_id: str, deleted_at: datetime):
        self.deletes.append((session, clerk_id, deleted_at))
        return True
