from fastapi import APIRouter

from backend.auth.dependencies import CurrentUserDep
from backend.auth.schemas import CurrentUserResponse

router = APIRouter(tags=["auth"])


@router.get(
    "/me",
    operation_id="getCurrentUser",
    summary="Get current user",
)
async def get_me(current_user: CurrentUserDep) -> CurrentUserResponse:
    return CurrentUserResponse.model_validate(current_user)
