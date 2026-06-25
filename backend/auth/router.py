"""Authentication API routes."""

from fastapi import APIRouter, status

from backend.auth.dependencies import BootstrapCurrentUserDep, SettingsDep, SignInTokenClientDep
from backend.auth.schemas import CurrentUser, DemoAdminSignInTokenResponse
from backend.core.exceptions import ApiError

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
async def create_demo_admin_sign_in_token(
    settings: SettingsDep,
    sign_in_token_client: SignInTokenClientDep,
) -> DemoAdminSignInTokenResponse:
    if not settings.demo_admin_login_enabled:
        raise ApiError(
            code="not_found",
            message="Not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    user_id = settings.demo_admin_clerk_user_id
    if not user_id or not user_id.strip():
        raise ApiError(
            code="demo_admin_login_not_configured",
            message="Demo admin login is not configured.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if not settings.clerk_secret_key:
        raise ApiError(
            code="clerk_secret_key_not_configured",
            message="Clerk sign-in token creation is not configured.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    token = await sign_in_token_client.create_sign_in_token(
        user_id=user_id.strip(),
        expires_in_seconds=settings.demo_admin_sign_in_token_ttl_seconds,
    )
    return DemoAdminSignInTokenResponse(token=token)
