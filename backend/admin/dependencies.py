from typing import Annotated

from fastapi import Depends, Header, status

from backend.admin.health_service import AdminHealthService
from backend.admin.service import AdminUsageService
from backend.core.database import DbSession
from backend.core.exceptions import ApiError


async def require_admin(
    x_admin_user: Annotated[str | None, Header(alias="X-Admin-User")] = None,
) -> None:
    if x_admin_user is None or x_admin_user.strip().lower() != "true":
        raise ApiError(
            code="admin_required",
            message="Admin access is required.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


def get_admin_usage_service(session: DbSession) -> AdminUsageService:
    return AdminUsageService(session=session)


def get_admin_health_service(session: DbSession) -> AdminHealthService:
    return AdminHealthService(session=session)


AdminUsageServiceDep = Annotated[AdminUsageService, Depends(get_admin_usage_service)]
AdminHealthServiceDep = Annotated[AdminHealthService, Depends(get_admin_health_service)]
