from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from backend.admin.dependencies import AdminHealthServiceDep, AdminUsageServiceDep, require_admin
from backend.admin.schemas import (
    AdminHealthResponse,
    AdminUsageSummaryResponse,
    CostComponentsResponse,
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
    "/usage/cost-components",
    operation_id="listAdminUsageCostComponents",
    summary="List admin usage cost components",
)
async def list_cost_components(
    service: AdminUsageServiceDep,
    from_date: Annotated[str | None, Query(alias="fromDate")] = None,
    to_date: Annotated[str | None, Query(alias="toDate")] = None,
    conversation_id: Annotated[UUID | None, Query(alias="conversationId")] = None,
    assistant_message_id: Annotated[UUID | None, Query(alias="assistantMessageId")] = None,
    component_type: Annotated[str | None, Query(alias="componentType")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CostComponentsResponse:
    return await service.list_cost_components(
        from_date=from_date,
        to_date=to_date,
        conversation_id=conversation_id,
        assistant_message_id=assistant_message_id,
        component_type=component_type,
        limit=limit,
        offset=offset,
    )
