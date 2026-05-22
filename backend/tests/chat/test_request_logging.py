import logging

import pytest
from httpx import ASGITransport, AsyncClient

from backend.core.config import settings
from backend.main import app


@pytest.mark.asyncio
async def test_request_middleware_generates_request_id(caplog) -> None:
    caplog.set_level(logging.INFO, logger="backend.core.observability.middleware")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    request_id = response.headers[settings.request_id_header]
    assert request_id
    completed = _event_records(caplog.records, "http.request.completed")
    assert completed
    assert completed[-1].request_id == request_id
    assert completed[-1].status_code == 200
    assert isinstance(completed[-1].latency_ms, int)


@pytest.mark.asyncio
async def test_request_middleware_preserves_request_id_header(caplog) -> None:
    caplog.set_level(logging.INFO, logger="backend.core.observability.middleware")
    request_id = "test-request-id"

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/health",
            headers={settings.request_id_header: request_id},
        )

    assert response.headers[settings.request_id_header] == request_id
    completed = _event_records(caplog.records, "http.request.completed")
    assert completed[-1].request_id == request_id


def _event_records(records, event: str):
    return [record for record in records if getattr(record, "event", None) == event]
