from datetime import date
from decimal import Decimal

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


def format_cost(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.000001")))
