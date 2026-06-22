from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from backend.auth.schemas import UserRole


class AdminBaseModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class UsageRange(AdminBaseModel):
    from_date: date
    to_date: date


class UsageMetrics(AdminBaseModel):
    total_users: int
    total_conversations: int
    user_queries: int
    assistant_responses: int
    failed_responses: int
    blocked_responses: int
    total_tokens: int
    estimated_cost_usd: str
    average_latency_ms: int | None


class DailyUsagePoint(AdminBaseModel):
    date: date
    user_queries: int
    assistant_responses: int
    total_tokens: int


class AdminUsageSummaryResponse(AdminBaseModel):
    range: UsageRange
    metrics: UsageMetrics
    daily_usage: list[DailyUsagePoint]


class AdminUserOverview(AdminBaseModel):
    display_name: str
    access_level: UserRole
    total_messages_sent: int
    blocked_requests: int
    last_activity: datetime | None


class AdminUserOverviewResponse(AdminBaseModel):
    users: list[AdminUserOverview]


class HealthStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    NOT_CHECKED = "not_checked"


class AdminHealthCheck(AdminBaseModel):
    id: str
    name: str
    status: HealthStatus
    latency_ms: int | None = None
    message: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class AdminHealthResponse(AdminBaseModel):
    status: HealthStatus
    checked_at: datetime
    checks: list[AdminHealthCheck]


def format_cost(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000001")), "f")
