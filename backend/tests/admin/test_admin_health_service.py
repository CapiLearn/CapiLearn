import asyncio
from datetime import UTC, datetime

import pytest

from backend.admin.health_service import (
    AdminHealthResponseCache,
    AdminHealthService,
    CachedLiteLLMProviderMetadataProvider,
    _aggregate_status,
    _provider_for_model,
    admin_health_response_cache,
)
from backend.admin.schemas import AdminHealthCheck, AdminHealthResponse, HealthStatus
from backend.llm.config import InputGuardrailMode, LLMSettings, OutputGuardrailMode
from backend.rag.config import RagBackend, RagSettings
from backend.rag.defaults import DEFAULT_RAG_MODEL_NAME


@pytest.fixture(autouse=True)
def clear_shared_health_cache():
    admin_health_response_cache.clear()
    yield
    admin_health_response_cache.clear()


@pytest.mark.asyncio
async def test_admin_health_reports_database_success() -> None:
    service = AdminHealthService(
        session=ScalarSession([1]),
        provider_metadata_provider=StaticModelProvider(["gpt-4o-mini"]),
        llm_config=LLMSettings(
            model="openai/gpt-4o-mini",
            guardrails_enabled=False,
        ),
        rag_config=RagSettings(),
        clock=lambda: datetime(2026, 6, 9, 12, tzinfo=UTC),
    )

    response = await service.get_health()

    database_check = _check(response.checks, "database")
    assert database_check.status == HealthStatus.OK
    assert database_check.latency_ms is not None


@pytest.mark.asyncio
async def test_admin_health_response_is_cached_for_short_ttl() -> None:
    cache = AdminHealthResponseCache(ttl_seconds=30)
    session = ScalarSession([1])
    provider = StaticModelProvider(["gpt-4o-mini"])
    service = AdminHealthService(
        session=session,
        provider_metadata_provider=provider,
        response_cache=cache,
        llm_config=LLMSettings(
            model="openai/gpt-4o-mini",
            guardrails_enabled=False,
        ),
        rag_config=RagSettings(),
        clock=lambda: datetime(2026, 6, 9, 12, tzinfo=UTC),
    )

    first_response = await service.get_health()
    first_response.checks[0].message = "mutated caller copy"
    second_response = await service.get_health()

    assert first_response.checked_at == second_response.checked_at
    assert second_response.checks[0].message == "Backend process is responding."
    assert len(session.scalar_statements) == 9
    assert provider.requested_providers == ["openai"]


@pytest.mark.asyncio
async def test_admin_health_response_cache_collapses_concurrent_loads() -> None:
    cache = AdminHealthResponseCache(ttl_seconds=30)
    loader = CountingHealthResponseLoader()

    first_response, second_response = await asyncio.gather(
        cache.get_or_load(loader),
        cache.get_or_load(loader),
    )

    assert first_response.checked_at == second_response.checked_at
    assert loader.calls == 1


@pytest.mark.asyncio
async def test_admin_health_reports_database_failure() -> None:
    service = AdminHealthService(
        session=FailingScalarSession(),
        provider_metadata_provider=StaticModelProvider(["gpt-4o-mini"]),
        llm_config=LLMSettings(
            model="openai/gpt-4o-mini",
            guardrails_enabled=False,
        ),
        rag_config=RagSettings(),
    )

    response = await service.get_health()

    assert _check(response.checks, "database").status == HealthStatus.UNHEALTHY
    assert response.status == HealthStatus.UNHEALTHY


@pytest.mark.asyncio
async def test_admin_health_reports_pgvector_rag_counts_and_missing_embeddings() -> None:
    session = ScalarSession(
        [
            1,
            2,
            5,
            4,
            1,
            4,
            1,
            datetime(2026, 6, 9, 11, tzinfo=UTC),
            datetime(2026, 6, 9, 11, 30, tzinfo=UTC),
        ]
    )
    service = AdminHealthService(
        session=session,
        provider_metadata_provider=StaticModelProvider(["gpt-4o-mini"]),
        llm_config=LLMSettings(
            model="openai/gpt-4o-mini",
            guardrails_enabled=False,
        ),
        rag_config=RagSettings(
            backend=RagBackend.PGVECTOR,
            model_name=DEFAULT_RAG_MODEL_NAME,
            index_version="v1",
        ),
    )

    response = await service.get_health()

    rag_check = _check(response.checks, "rag")
    assert rag_check.status == HealthStatus.DEGRADED
    assert rag_check.details["documents"] == 2
    assert rag_check.details["chunks"] == 5
    assert rag_check.details["embeddings"] == 4
    assert rag_check.details["chunksMissingEmbeddings"] == 1
    assert rag_check.details["configuredModelEmbeddings"] == 4
    assert rag_check.details["chunksMissingConfiguredModelEmbeddings"] == 1
    assert rag_check.details["latestDocumentUpdatedAt"] == "2026-06-09T11:00:00+00:00"


@pytest.mark.asyncio
async def test_pgvector_rag_is_degraded_when_only_old_model_embeddings_exist() -> None:
    service = AdminHealthService(
        session=ScalarSession(
            [
                2,
                5,
                5,
                0,
                0,
                5,
                datetime(2026, 6, 9, 11, tzinfo=UTC),
                None,
            ]
        ),
        provider_metadata_provider=StaticModelProvider(["gpt-4o-mini"]),
        llm_config=LLMSettings(
            model="openai/gpt-4o-mini",
            guardrails_enabled=False,
        ),
        rag_config=RagSettings(
            backend=RagBackend.PGVECTOR,
            model_name=DEFAULT_RAG_MODEL_NAME,
        ),
    )

    rag_check = await service._check_rag()

    assert rag_check.status == HealthStatus.DEGRADED
    assert rag_check.details["chunks"] == 5
    assert rag_check.details["embeddings"] == 5
    assert rag_check.details["chunksMissingEmbeddings"] == 0
    assert rag_check.details["configuredModelEmbeddings"] == 0
    assert rag_check.details["chunksMissingConfiguredModelEmbeddings"] == 5


@pytest.mark.asyncio
async def test_pgvector_rag_is_ok_when_all_chunks_have_configured_model_embeddings() -> None:
    service = AdminHealthService(
        session=ScalarSession(
            [
                2,
                5,
                7,
                0,
                5,
                0,
                datetime(2026, 6, 9, 11, tzinfo=UTC),
                None,
            ]
        ),
        provider_metadata_provider=StaticModelProvider(["gpt-4o-mini"]),
        llm_config=LLMSettings(
            model="openai/gpt-4o-mini",
            guardrails_enabled=False,
        ),
        rag_config=RagSettings(
            backend=RagBackend.PGVECTOR,
            model_name=DEFAULT_RAG_MODEL_NAME,
        ),
    )

    rag_check = await service._check_rag()

    assert rag_check.status == HealthStatus.OK
    assert rag_check.details["configuredModelEmbeddings"] == 5
    assert rag_check.details["chunksMissingConfiguredModelEmbeddings"] == 0


@pytest.mark.asyncio
async def test_guardrails_regex_or_off_is_ok_without_provider_metadata_call() -> None:
    provider = StaticModelProvider([])
    service = AdminHealthService(
        session=ScalarSession([]),
        provider_metadata_provider=provider,
        llm_config=LLMSettings(
            guardrails_enabled=True,
            input_guardrail_mode=InputGuardrailMode.REGEX,
            output_guardrail_mode=OutputGuardrailMode.OFF,
            guardrails_judge_enabled=True,
        ),
        rag_config=RagSettings(),
    )

    check = await service._check_guardrails()

    assert check.status == HealthStatus.OK
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_guardrails_policy_uses_provider_metadata_without_completion_call() -> None:
    provider = StaticModelProvider(["gpt-4o-mini"])
    service = AdminHealthService(
        session=ScalarSession([]),
        provider_metadata_provider=provider,
        llm_config=LLMSettings(
            guardrails_enabled=True,
            input_guardrail_mode=InputGuardrailMode.POLICY,
            output_guardrail_mode=OutputGuardrailMode.POLICY,
            guardrails_judge_enabled=True,
            guardrails_judge_model="openai/gpt-4o-mini",
        ),
        rag_config=RagSettings(),
    )

    check = await service._check_guardrails()

    assert check.status == HealthStatus.OK
    assert check.details["configuredModel"] == "openai/gpt-4o-mini"
    assert check.details["provider"] == "openai"
    assert check.details["providerAvailable"] is True
    assert provider.calls == 1
    assert provider.requested_providers == ["openai"]


@pytest.mark.asyncio
async def test_llm_provider_metadata_empty_model_list_is_degraded() -> None:
    service = AdminHealthService(
        session=ScalarSession([]),
        provider_metadata_provider=StaticModelProvider([]),
        llm_config=LLMSettings(model="openai/gpt-4o-mini"),
        rag_config=RagSettings(),
    )

    check = await service._check_llm_provider_metadata()

    assert check.status == HealthStatus.DEGRADED
    assert check.details["returnedModelCount"] == 0
    assert check.details["providerAvailable"] is False


@pytest.mark.asyncio
async def test_llm_provider_metadata_does_not_require_exact_configured_model() -> None:
    provider = StaticModelProvider({"openai": ["gpt-4o"]})
    service = AdminHealthService(
        session=ScalarSession([]),
        provider_metadata_provider=provider,
        llm_config=LLMSettings(model="openai/gpt-4o-mini"),
        rag_config=RagSettings(),
    )

    check = await service._check_llm_provider_metadata()

    assert check.status == HealthStatus.OK
    assert check.details == {
        "configuredModel": "openai/gpt-4o-mini",
        "provider": "openai",
        "returnedModelCount": 1,
        "providerAvailable": True,
    }
    assert provider.requested_providers == ["openai"]


@pytest.mark.asyncio
async def test_llm_provider_metadata_failure_is_degraded() -> None:
    service = AdminHealthService(
        session=ScalarSession([]),
        provider_metadata_provider=FailingModelProvider(),
        llm_config=LLMSettings(model="openai/gpt-4o-mini"),
        rag_config=RagSettings(),
    )

    check = await service._check_llm_provider_metadata()

    assert check.status == HealthStatus.DEGRADED
    assert check.message == (
        "Configured LLM provider metadata check failed; provider liveness could not be confirmed."
    )
    assert check.details == {
        "configuredModel": "openai/gpt-4o-mini",
        "provider": "openai",
        "returnedModelCount": 0,
        "providerAvailable": False,
    }


@pytest.mark.asyncio
async def test_provider_metadata_result_is_cached_within_request_for_same_provider() -> None:
    provider = StaticModelProvider({"openai": ["gpt-4o-mini"]})
    service = AdminHealthService(
        session=ScalarSession([1]),
        provider_metadata_provider=provider,
        llm_config=LLMSettings(
            model="openai/gpt-4o-mini",
            guardrails_enabled=True,
            input_guardrail_mode=InputGuardrailMode.POLICY,
            output_guardrail_mode=OutputGuardrailMode.POLICY,
            guardrails_judge_enabled=True,
            guardrails_judge_model="openai/gpt-4o",
        ),
        rag_config=RagSettings(),
    )

    response = await service.get_health()

    assert _check(response.checks, "llmProviderMetadata").status == HealthStatus.OK
    assert _check(response.checks, "guardrails").status == HealthStatus.OK
    assert provider.requested_providers == ["openai"]


@pytest.mark.asyncio
async def test_provider_metadata_checks_main_and_guardrail_judge_providers_separately() -> None:
    provider = StaticModelProvider(
        {
            "openai": ["gpt-4o-mini"],
            "gemini": ["gemini-1.5-flash"],
        }
    )
    service = AdminHealthService(
        session=ScalarSession([1]),
        provider_metadata_provider=provider,
        llm_config=LLMSettings(
            model="openai/gpt-4o-mini",
            guardrails_enabled=True,
            input_guardrail_mode=InputGuardrailMode.POLICY,
            output_guardrail_mode=OutputGuardrailMode.POLICY,
            guardrails_judge_enabled=True,
            guardrails_judge_model="gemini/gemini-1.5-flash",
        ),
        rag_config=RagSettings(),
    )

    response = await service.get_health()

    assert _check(response.checks, "llmProviderMetadata").details["provider"] == "openai"
    assert _check(response.checks, "guardrails").details["provider"] == "gemini"
    assert provider.requested_providers == ["openai", "gemini"]


@pytest.mark.asyncio
async def test_provider_metadata_result_is_cached_per_provider() -> None:
    loader = CountingModelLoader()
    cached_provider = CachedLiteLLMProviderMetadataProvider(
        ttl_seconds=300,
        model_loader=loader,
    )

    first_openai_call = await cached_provider.get_models("openai")
    gemini_call = await cached_provider.get_models("gemini")
    second_openai_call = await cached_provider.get_models("openai")

    assert first_openai_call == ["openai-model"]
    assert gemini_call == ["gemini-model"]
    assert second_openai_call == ["openai-model"]
    assert loader.requested_providers == ["openai", "gemini"]


def test_provider_for_model_uses_litellm_provider_resolution() -> None:
    assert _provider_for_model("openai/gpt-4o-mini") == "openai"


def test_aggregate_status_precedence() -> None:
    assert (
        _aggregate_status(
            [
                AdminHealthCheck(name="backend", status=HealthStatus.OK),
                AdminHealthCheck(name="rag", status=HealthStatus.DEGRADED),
            ]
        )
        == HealthStatus.DEGRADED
    )
    assert (
        _aggregate_status(
            [
                AdminHealthCheck(name="backend", status=HealthStatus.OK),
                AdminHealthCheck(name="database", status=HealthStatus.UNHEALTHY),
            ]
        )
        == HealthStatus.UNHEALTHY
    )
    assert (
        _aggregate_status([AdminHealthCheck(name="rag", status=HealthStatus.NOT_CHECKED)])
        == HealthStatus.NOT_CHECKED
    )


def _check(checks: list[AdminHealthCheck], name: str) -> AdminHealthCheck:
    for check in checks:
        if check.name == name:
            return check
    raise AssertionError(f"Missing health check: {name}")


class ScalarSession:
    def __init__(self, scalar_results: list) -> None:
        self.scalar_results = list(scalar_results)
        self.scalar_statements = []

    async def scalar(self, statement):
        self.scalar_statements.append(statement)
        if not self.scalar_results:
            return None
        return self.scalar_results.pop(0)


class FailingScalarSession:
    async def scalar(self, statement):
        raise RuntimeError("database unavailable")


class StaticModelProvider:
    def __init__(self, models: list[str] | dict[str, list[str]]) -> None:
        self.models = models
        self.calls = 0
        self.requested_providers = []

    async def get_models(self, provider: str) -> list[str]:
        self.calls += 1
        self.requested_providers.append(provider)
        if isinstance(self.models, dict):
            return list(self.models.get(provider, []))
        return list(self.models)


class FailingModelProvider:
    async def get_models(self, provider: str) -> list[str]:
        raise RuntimeError("provider failure with possible sensitive text")


class CountingModelLoader:
    def __init__(self) -> None:
        self.requested_providers = []

    def __call__(self, provider: str) -> list[str]:
        self.requested_providers.append(provider)
        return [f"{provider}-model"]


class CountingHealthResponseLoader:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self) -> AdminHealthResponse:
        self.calls += 1
        await asyncio.sleep(0)
        return AdminHealthResponse(
            status=HealthStatus.OK,
            checked_at=datetime(2026, 6, 9, 12, tzinfo=UTC),
            checks=[AdminHealthCheck(name="backend", status=HealthStatus.OK)],
        )
