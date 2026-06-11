import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Protocol

from litellm import get_llm_provider, get_valid_models
from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.admin.schemas import AdminHealthCheck, AdminHealthResponse, HealthStatus
from backend.core.observability import elapsed_ms, timer_start
from backend.llm.config import (
    InputGuardrailMode,
    LLMSettings,
    OutputGuardrailMode,
    llm_settings,
)
from backend.rag.config import RagBackend, RagSettings, rag_settings
from backend.rag.models import RagChunk, RagDocument, RagEmbedding, RagRetrievalLog

PROVIDER_METADATA_CACHE_TTL_SECONDS = 300
ADMIN_HEALTH_CACHE_TTL_SECONDS = 30


class ProviderMetadataProvider(Protocol):
    async def get_models(self, provider: str) -> list[str]: ...


class AdminHealthResponseCache:
    def __init__(self, *, ttl_seconds: int = ADMIN_HEALTH_CACHE_TTL_SECONDS) -> None:
        self._ttl_seconds = ttl_seconds
        self._response: AdminHealthResponse | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    async def get_or_load(
        self,
        loader: Callable[[], Awaitable[AdminHealthResponse]],
    ) -> AdminHealthResponse:
        now = time.monotonic()
        if self._response is not None and now < self._expires_at:
            return self._response.model_copy(deep=True)

        async with self._lock:
            now = time.monotonic()
            if self._response is not None and now < self._expires_at:
                return self._response.model_copy(deep=True)

            response = await loader()
            self._response = response.model_copy(deep=True)
            self._expires_at = time.monotonic() + self._ttl_seconds
            return self._response.model_copy(deep=True)

    def clear(self) -> None:
        self._response = None
        self._expires_at = 0.0


class CachedLiteLLMProviderMetadataProvider:
    def __init__(
        self,
        *,
        ttl_seconds: int = PROVIDER_METADATA_CACHE_TTL_SECONDS,
        model_loader: Callable[[str], list[str]] | None = None,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._model_loader = model_loader or _load_valid_models
        self._models_by_provider: dict[str, list[str]] = {}
        self._expires_at_by_provider: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def get_models(self, provider: str) -> list[str]:
        now = time.monotonic()
        if provider in self._models_by_provider and now < self._expires_at_by_provider.get(
            provider, 0.0
        ):
            return list(self._models_by_provider[provider])

        async with self._lock:
            now = time.monotonic()
            if provider in self._models_by_provider and now < self._expires_at_by_provider.get(
                provider, 0.0
            ):
                return list(self._models_by_provider[provider])

            models = await asyncio.to_thread(self._model_loader, provider)
            self._models_by_provider[provider] = list(models)
            self._expires_at_by_provider[provider] = time.monotonic() + self._ttl_seconds
            return list(self._models_by_provider[provider])

    def clear(self) -> None:
        self._models_by_provider.clear()
        self._expires_at_by_provider.clear()


def _load_valid_models(provider: str) -> list[str]:
    return get_valid_models(
        check_provider_endpoint=True,
        custom_llm_provider=provider,
    )


provider_metadata_provider = CachedLiteLLMProviderMetadataProvider()
admin_health_response_cache = AdminHealthResponseCache()


class AdminHealthService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        provider_metadata_provider: ProviderMetadataProvider = provider_metadata_provider,
        response_cache: AdminHealthResponseCache = admin_health_response_cache,
        llm_config: LLMSettings = llm_settings,
        rag_config: RagSettings = rag_settings,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session = session
        self._provider_metadata_provider = provider_metadata_provider
        self._response_cache = response_cache
        self._llm_config = llm_config
        self._rag_config = rag_config
        self._clock = clock or (lambda: datetime.now(UTC))
        self._provider_models: dict[str, list[str]] = {}

    async def get_health(self) -> AdminHealthResponse:
        return await self._response_cache.get_or_load(self._load_health)

    async def _load_health(self) -> AdminHealthResponse:
        checks = [
            self._check_backend(),
            await self._check_database(),
            await self._check_rag(),
            await self._check_llm_provider_metadata(),
            await self._check_guardrails(),
        ]
        return AdminHealthResponse(
            status=_aggregate_status(checks),
            checked_at=self._clock(),
            checks=checks,
        )

    def _check_backend(self) -> AdminHealthCheck:
        return AdminHealthCheck(
            name="backend",
            status=HealthStatus.OK,
            message="Backend process is responding.",
        )

    async def _check_database(self) -> AdminHealthCheck:
        started_at = timer_start()
        try:
            value = await self._session.scalar(text("SELECT 1"))
        except Exception:
            return AdminHealthCheck(
                name="database",
                status=HealthStatus.UNHEALTHY,
                latency_ms=elapsed_ms(started_at),
                message="Database connectivity check failed.",
            )

        if value != 1:
            return AdminHealthCheck(
                name="database",
                status=HealthStatus.UNHEALTHY,
                latency_ms=elapsed_ms(started_at),
                message="Database connectivity check returned an unexpected result.",
            )
        return AdminHealthCheck(
            name="database",
            status=HealthStatus.OK,
            latency_ms=elapsed_ms(started_at),
            message="Database connectivity check succeeded.",
        )

    async def _check_rag(self) -> AdminHealthCheck:
        if self._rag_config.backend == RagBackend.CHROMA:
            return AdminHealthCheck(
                name="rag",
                status=HealthStatus.NOT_CHECKED,
                message="Chroma RAG backend does not expose a cheap admin health probe.",
                details={
                    "backend": self._rag_config.backend.value,
                    "modelName": self._rag_config.model_name,
                    "indexVersion": self._rag_config.index_version,
                },
            )

        started_at = timer_start()
        try:
            document_count = await self._count(RagDocument.id)
            chunk_count = await self._count(RagChunk.id)
            embedding_count = await self._count(RagEmbedding.id)
            chunks_missing_embeddings = await self._count_chunks_missing_embeddings()
            configured_model_embedding_count = await self._count_configured_model_embeddings()
            chunks_missing_configured_model_embeddings = (
                await self._count_chunks_missing_configured_model_embeddings()
            )
            latest_document_updated_at = await self._session.scalar(
                select(func.max(RagDocument.updated_at))
            )
            latest_retrieval_log_created_at = await self._session.scalar(
                select(func.max(RagRetrievalLog.created_at))
            )
        except Exception:
            return AdminHealthCheck(
                name="rag",
                status=HealthStatus.UNHEALTHY,
                latency_ms=elapsed_ms(started_at),
                message="RAG storage health check failed.",
                details={
                    "backend": self._rag_config.backend.value,
                    "modelName": self._rag_config.model_name,
                    "indexVersion": self._rag_config.index_version,
                },
            )

        status = (
            HealthStatus.DEGRADED
            if chunk_count > 0 and chunks_missing_configured_model_embeddings > 0
            else HealthStatus.OK
        )
        message = (
            "RAG storage has chunks missing configured model embeddings."
            if status == HealthStatus.DEGRADED
            else "RAG storage counts are available."
        )
        return AdminHealthCheck(
            name="rag",
            status=status,
            latency_ms=elapsed_ms(started_at),
            message=message,
            details={
                "backend": self._rag_config.backend.value,
                "modelName": self._rag_config.model_name,
                "indexVersion": self._rag_config.index_version,
                "documents": document_count,
                "chunks": chunk_count,
                "embeddings": embedding_count,
                "chunksMissingEmbeddings": chunks_missing_embeddings,
                "configuredModelEmbeddings": configured_model_embedding_count,
                "chunksMissingConfiguredModelEmbeddings": (
                    chunks_missing_configured_model_embeddings
                ),
                "latestDocumentUpdatedAt": latest_document_updated_at.isoformat()
                if latest_document_updated_at
                else None,
                "latestRetrievalLogCreatedAt": latest_retrieval_log_created_at.isoformat()
                if latest_retrieval_log_created_at
                else None,
            },
        )

    async def _check_llm_provider_metadata(self) -> AdminHealthCheck:
        return await self._build_provider_metadata_check(
            name="llmProviderMetadata",
            model=self._llm_config.model,
            ok_message="Configured LLM provider returned model metadata.",
            unresolved_message=(
                "Configured LLM provider could not be resolved; provider liveness "
                "could not be confirmed."
            ),
            failed_message=(
                "Configured LLM provider metadata check failed; provider liveness "
                "could not be confirmed."
            ),
            empty_message=(
                "Configured LLM provider returned no model metadata; provider liveness "
                "could not be confirmed."
            ),
        )

    async def _check_guardrails(self) -> AdminHealthCheck:
        details = {
            "enabled": self._llm_config.guardrails_enabled,
            "inputMode": self._llm_config.input_guardrail_mode.value,
            "outputMode": self._llm_config.output_guardrail_mode.value,
            "judgeEnabled": self._llm_config.guardrails_judge_enabled,
        }
        if not self._guardrails_need_provider_metadata():
            return AdminHealthCheck(
                name="guardrails",
                status=HealthStatus.OK,
                message="Guardrails configuration does not require a live judge model check.",
                details=details,
            )

        check = await self._build_provider_metadata_check(
            name="guardrails",
            model=self._llm_config.guardrails_judge_model,
            ok_message="Guardrail judge provider returned model metadata.",
            unresolved_message=(
                "Guardrail judge provider could not be resolved; provider liveness "
                "could not be confirmed."
            ),
            failed_message=(
                "Guardrail judge provider metadata check failed; provider liveness "
                "could not be confirmed."
            ),
            empty_message=(
                "Guardrail judge provider returned no model metadata; provider liveness "
                "could not be confirmed."
            ),
        )
        check.details.update(details)
        return check

    def _guardrails_need_provider_metadata(self) -> bool:
        if not self._llm_config.guardrails_enabled:
            return False
        if not self._llm_config.guardrails_judge_enabled:
            return False
        input_needs_judge = self._llm_config.input_guardrail_mode == InputGuardrailMode.POLICY
        output_needs_judge = self._llm_config.output_guardrail_mode == OutputGuardrailMode.POLICY
        return input_needs_judge or output_needs_judge

    async def _build_provider_metadata_check(
        self,
        *,
        name: str,
        model: str,
        ok_message: str,
        unresolved_message: str,
        failed_message: str,
        empty_message: str,
    ) -> AdminHealthCheck:
        started_at = timer_start()
        try:
            provider = _provider_for_model(model)
        except Exception:
            return AdminHealthCheck(
                name=name,
                status=HealthStatus.DEGRADED,
                latency_ms=elapsed_ms(started_at),
                message=unresolved_message,
                details={
                    "configuredModel": model,
                    "provider": None,
                    "returnedModelCount": 0,
                    "providerAvailable": False,
                },
            )

        details = {
            "configuredModel": model,
            "provider": provider,
            "returnedModelCount": 0,
        }
        try:
            models = await self._get_provider_models(provider)
        except Exception:
            return AdminHealthCheck(
                name=name,
                status=HealthStatus.DEGRADED,
                latency_ms=elapsed_ms(started_at),
                message=failed_message,
                details={
                    **details,
                    "providerAvailable": False,
                },
            )

        details = {
            **details,
            "returnedModelCount": len(models),
        }
        if not models:
            return AdminHealthCheck(
                name=name,
                status=HealthStatus.DEGRADED,
                latency_ms=elapsed_ms(started_at),
                message=empty_message,
                details={
                    **details,
                    "providerAvailable": False,
                },
            )
        return AdminHealthCheck(
            name=name,
            status=HealthStatus.OK,
            latency_ms=elapsed_ms(started_at),
            message=ok_message,
            details={
                **details,
                "providerAvailable": True,
            },
        )

    async def _get_provider_models(self, provider: str) -> list[str]:
        if provider not in self._provider_models:
            self._provider_models[provider] = await self._provider_metadata_provider.get_models(
                provider
            )
        return list(self._provider_models[provider])

    async def _count(self, column) -> int:
        value = await self._session.scalar(select(func.count(column)))
        return int(value or 0)

    async def _count_chunks_missing_embeddings(self) -> int:
        value = await self._session.scalar(
            select(func.count(RagChunk.id))
            .outerjoin(RagEmbedding, RagEmbedding.chunk_id == RagChunk.id)
            .where(RagEmbedding.id.is_(None))
        )
        return int(value or 0)

    async def _count_configured_model_embeddings(self) -> int:
        value = await self._session.scalar(
            select(func.count(RagEmbedding.id)).where(
                RagEmbedding.embedding_model == self._rag_config.model_name
            )
        )
        return int(value or 0)

    async def _count_chunks_missing_configured_model_embeddings(self) -> int:
        value = await self._session.scalar(
            select(func.count(RagChunk.id))
            .outerjoin(
                RagEmbedding,
                and_(
                    RagEmbedding.chunk_id == RagChunk.id,
                    RagEmbedding.embedding_model == self._rag_config.model_name,
                ),
            )
            .where(RagEmbedding.id.is_(None))
        )
        return int(value or 0)


def _provider_for_model(model: str) -> str:
    _, provider, _, _ = get_llm_provider(model)
    if not provider:
        raise ValueError("LiteLLM did not resolve a provider for the configured model.")
    return provider


def _aggregate_status(checks: list[AdminHealthCheck]) -> HealthStatus:
    statuses = {check.status for check in checks}
    if HealthStatus.UNHEALTHY in statuses:
        return HealthStatus.UNHEALTHY
    if HealthStatus.DEGRADED in statuses:
        return HealthStatus.DEGRADED
    if HealthStatus.OK in statuses:
        return HealthStatus.OK
    return HealthStatus.NOT_CHECKED
