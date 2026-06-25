"""Authentication API routes."""

from fastapi import APIRouter, Request, status

from backend.auth.dependencies import BootstrapCurrentUserDep, SettingsDep, SignInTokenClientDep
from backend.auth.schemas import CurrentUser, DemoAdminSignInTokenResponse
from backend.core.exceptions import ApiError
from backend.core.rate_limiting import (
    DEMO_ADMIN_LOGIN_RATE_LIMIT,
    DEMO_ADMIN_LOGIN_RATE_LIMIT_SCOPE,
    ip_rate_limit_key,
    limiter,
)

router = APIRouter(tags=["auth"])


@router.get(
    "/me",
    operation_id="getCurrentUser",
    summary="Bootstrap current user",
)
async def get_me(current_user: BootstrapCurrentUserDep) -> CurrentUser:
    """Return the signed-in user, creating the local account on first use."""
    return current_user


@router.post(
    "/auth/demo-admin/sign-in-token",
    operation_id="createDemoAdminSignInToken",
    summary="Create demo admin sign-in token",
)
@limiter.shared_limit(
    DEMO_ADMIN_LOGIN_RATE_LIMIT,
    scope=DEMO_ADMIN_LOGIN_RATE_LIMIT_SCOPE,
    key_func=ip_rate_limit_key,
)
async def create_demo_admin_sign_in_token(
    request: Request,
    settings: SettingsDep,
    sign_in_token_client: SignInTokenClientDep,
) -> DemoAdminSignInTokenResponse:
    if not settings.demo_admin_login_enabled:
        raise ApiError(
            code="not_found",
            message="Not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    email_address = settings.demo_admin_email
    if not email_address.strip():
        raise ApiError(
            code="demo_admin_login_not_configured",
            message="Demo admin login is not configured.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    token = await sign_in_token_client.create_sign_in_token_for_email(
        email_address=email_address.strip(),
        expires_in_seconds=settings.demo_admin_sign_in_token_ttl_seconds,
    )
    return DemoAdminSignInTokenResponse(token=token)
