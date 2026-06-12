from typing import Annotated

from fastapi import Depends

from backend.admin.health_service import AdminHealthService
from backend.admin.service import AdminUsageService
from backend.auth.dependencies import require_admin as require_admin
from backend.core.database import DbSession


def get_admin_usage_service(session: DbSession) -> AdminUsageService:
    return AdminUsageService(session=session)


def get_admin_health_service(session: DbSession) -> AdminHealthService:
    return AdminHealthService(session=session)


AdminUsageServiceDep = Annotated[AdminUsageService, Depends(get_admin_usage_service)]
AdminHealthServiceDep = Annotated[AdminHealthService, Depends(get_admin_health_service)]
