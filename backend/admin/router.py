from typing import Annotated

from fastapi import APIRouter, Depends, Query

from backend.admin.dependencies import AdminUsageServiceDep, require_admin
from backend.admin.schemas import AdminUsageSummaryResponse

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


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
