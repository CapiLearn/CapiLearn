from typing import Annotated

from fastapi import APIRouter, Depends, Query

from backend.admin.dependencies import AdminHealthServiceDep, AdminUsageServiceDep, require_admin
from backend.admin.schemas import (
    AdminHealthResponse,
    AdminUsageSummaryResponse,
    AdminUserOverviewResponse,
)

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


@router.get(
    "/health",
    operation_id="getAdminHealth",
    summary="Get admin health status",
)
async def get_admin_health(service: AdminHealthServiceDep) -> AdminHealthResponse:
    return await service.get_health()


@router.get(
    "/usage/summary",
    operation_id="getAdminUsageSummary",
    summary="Get admin usage summary",
)
async def get_usage_summary(
    service: AdminUsageServiceDep,
    from_date: Annotated[str | None, Query(alias="fromDate")] = None,
    to_date: Annotated[str | None, Query(alias="toDate")] = None,
) -> AdminUsageSummaryResponse:
    return await service.get_usage_summary(from_date=from_date, to_date=to_date)


@router.get(
    "/users/overview",
    operation_id="listAdminUserOverviews",
    summary="List admin user activity overviews",
)
async def list_user_overviews(
    service: AdminUsageServiceDep,
    from_date: Annotated[str | None, Query(alias="fromDate")] = None,
    to_date: Annotated[str | None, Query(alias="toDate")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdminUserOverviewResponse:
    return await service.list_user_overviews(
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset,
    )
