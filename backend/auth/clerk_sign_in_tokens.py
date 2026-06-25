from typing import Protocol

import clerk_backend_api
from clerk_backend_api import Clerk
from fastapi import status

from backend.core.config import Settings
from backend.core.exceptions import ApiError


class SignInTokenClient(Protocol):
    async def create_sign_in_token_for_email(
        self,
        *,
        email_address: str,
        expires_in_seconds: int,
    ) -> str: ...


class ClerkSignInTokenClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def create_sign_in_token_for_email(
        self,
        *,
        email_address: str,
        expires_in_seconds: int,
    ) -> str:
        if not self._settings.clerk_secret_key:
            raise ApiError(
                code="clerk_secret_key_not_configured",
                message="Clerk sign-in token creation is not configured.",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        email_address = email_address.strip()
        sdk = Clerk(bearer_auth=self._settings.clerk_secret_key)
        user_id = await self._get_user_id_by_email(sdk, email_address)
        return await self._create_sign_in_token(
            sdk,
            user_id=user_id,
            expires_in_seconds=expires_in_seconds,
        )

    async def _get_user_id_by_email(self, sdk: Clerk, email_address: str) -> str:
        try:
            users = await sdk.users.list_async(
                request={
                    "email_address": [email_address],
                    "limit": 2,
                }
            )
        except clerk_backend_api.ClerkErrors as exc:
            raise ApiError(
                code="clerk_demo_admin_lookup_failed",
                message="Unable to find demo admin user.",
                status_code=status.HTTP_502_BAD_GATEWAY,
                details=_clerk_error_details(exc),
            ) from exc
        except clerk_backend_api.SDKError as exc:
            raise ApiError(
                code="clerk_demo_admin_lookup_failed",
                message="Unable to find demo admin user.",
                status_code=status.HTTP_502_BAD_GATEWAY,
            ) from exc

        if len(users) != 1:
            raise ApiError(
                code="demo_admin_login_not_configured",
                message="Demo admin login is not configured.",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return users[0].id

    async def _create_sign_in_token(
        self,
        sdk: Clerk,
        *,
        user_id: str,
        expires_in_seconds: int,
    ) -> str:
        try:
            sign_in_token = await sdk.sign_in_tokens.create_async(
                request={
                    "user_id": user_id,
                    "expires_in_seconds": expires_in_seconds,
                }
            )
        except clerk_backend_api.ClerkErrors as exc:
            raise ApiError(
                code="clerk_sign_in_token_failed",
                message="Unable to create demo admin sign-in token.",
                status_code=status.HTTP_502_BAD_GATEWAY,
                details=_clerk_error_details(exc),
            ) from exc
        except clerk_backend_api.SDKError as exc:
            raise ApiError(
                code="clerk_sign_in_token_failed",
                message="Unable to create demo admin sign-in token.",
                status_code=status.HTTP_502_BAD_GATEWAY,
            ) from exc

        if not sign_in_token.token:
            raise ApiError(
                code="clerk_sign_in_token_missing",
                message="Clerk did not return a demo admin sign-in token.",
                status_code=status.HTTP_502_BAD_GATEWAY,
            )

        return sign_in_token.token


def _clerk_error_details(exc: clerk_backend_api.ClerkErrors) -> dict[str, object]:
    return {
        "errors": [
            {
                "code": error.code,
                "message": error.message,
            }
            for error in exc.data.errors
        ]
    }
