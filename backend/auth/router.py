"""Authentication API routes."""

from fastapi import APIRouter

from backend.auth.dependencies import BootstrapCurrentUserDep
from backend.auth.schemas import CurrentUser

router = APIRouter(tags=["auth"])


@router.get(
    "/me",
    operation_id="getCurrentUser",
    summary="Bootstrap current user",
)
async def get_me(current_user: BootstrapCurrentUserDep) -> CurrentUser:
    """Return the signed-in user, creating the local account on first use."""
    return current_user
