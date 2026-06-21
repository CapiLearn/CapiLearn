from binascii import Error as BinasciiError
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response, status
from svix.webhooks import Webhook, WebhookVerificationError

from backend.auth.clerk_webhook_service import ClerkWebhookService
from backend.core.config import Settings, get_settings
from backend.core.database import DbSession
from backend.core.exceptions import ApiError

router = APIRouter(tags=["webhooks"])


def get_clerk_webhook_service() -> ClerkWebhookService:
    return ClerkWebhookService()


SettingsDep = Annotated[Settings, Depends(get_settings)]
ClerkWebhookServiceDep = Annotated[
    ClerkWebhookService,
    Depends(get_clerk_webhook_service),
]


@router.post(
    "/webhooks/clerk",
    operation_id="handleClerkWebhook",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Handle Clerk webhook",
)
async def handle_clerk_webhook(
    request: Request,
    session: DbSession,
    settings: SettingsDep,
    service: ClerkWebhookServiceDep,
) -> Response:
    event = await verify_clerk_webhook(request, settings=settings)
    await service.handle_event(session, event)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def verify_clerk_webhook(request: Request, *, settings: Settings) -> dict[str, Any]:
    if not settings.clerk_webhook_signing_secret:
        raise ApiError(
            code="webhook_not_configured",
            message="Clerk webhook signing secret is not configured.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    payload = await request.body()
    try:
        event = Webhook(settings.clerk_webhook_signing_secret).verify(
            payload,
            dict(request.headers),
        )
    except (BinasciiError, WebhookVerificationError) as exc:
        raise ApiError(
            code="invalid_webhook_signature",
            message="Invalid Clerk webhook signature.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    if not isinstance(event, dict):
        raise ApiError(
            code="invalid_webhook_payload",
            message="Invalid Clerk webhook payload.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return event
