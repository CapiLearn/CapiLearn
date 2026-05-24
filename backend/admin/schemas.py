from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


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


class CostComponentResponse(AdminBaseModel):
    id: UUID
    user_id: UUID
    conversation_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID
    component_order: int
    component_type: str
    attempt_index: int
    provider: str | None
    configured_model: str | None
    response_model: str | None
    finish_reason: str | None
    status: str
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    estimated_cost_usd: str | None
    latency_ms: int | None
    error_type: str | None
    metadata: dict
    created_at: datetime


class CostComponentsResponse(AdminBaseModel):
    range: UsageRange
    cost_components: list[CostComponentResponse]


def format_cost(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000001")), "f")


def format_component_cost(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.quantize(Decimal("0.000000000001")), "f")
