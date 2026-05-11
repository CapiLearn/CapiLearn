from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, status

from backend.auth.schemas import CurrentUser
from backend.core.config import settings
from backend.core.exceptions import ApiError


async def get_current_user(
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
    x_user_email: Annotated[str | None, Header(alias="X-User-Email")] = None,
) -> CurrentUser:
    if x_user_id is None:
        return CurrentUser(id=settings.local_dev_user_id, email=x_user_email)

    try:
        user_id = UUID(x_user_id)
    except ValueError as exc:
        raise ApiError(
            code="invalid_user_header",
            message="X-User-Id must be a valid UUID.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        ) from exc

    return CurrentUser(id=user_id, email=x_user_email)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
