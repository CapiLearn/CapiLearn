import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.rag.config import RagBackend, RagEmbeddingProvider, RagSettings
from backend.rag.embeddings import OpenAIEmbeddingProvider, build_embedding_provider


def test_pgvector_is_the_only_supported_runtime_backend() -> None:
    settings = RagSettings(_env_file=None)

    assert settings.backend == RagBackend.PGVECTOR
    assert settings.corpus_source_path == Path("backend/rag/source_corpus/fullstack_hy2020")


def test_corpus_source_path_environment_is_respected(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RAG_CORPUS_SOURCE_PATH", str(tmp_path))

    settings = RagSettings(_env_file=None)

    assert settings.corpus_source_path == tmp_path


def test_chroma_runtime_backend_is_rejected() -> None:
    with pytest.raises(ValidationError, match="Chroma is no longer a supported runtime"):
        RagSettings(_env_file=None, backend="chroma")


def test_unknown_runtime_backend_is_rejected() -> None:
    with pytest.raises(ValidationError, match="backend"):
        RagSettings(_env_file=None, backend="unknown")


def test_openai_embedding_provider_is_selected_from_config() -> None:
    settings = RagSettings(
        _env_file=None,
        backend=RagBackend.PGVECTOR,
        embedding_provider=RagEmbeddingProvider.OPENAI,
        model_name="text-embedding-3-small",
        embedding_dimensions=384,
        OPENAI_API_KEY="test-key",
    )

    provider = build_embedding_provider(settings)

    assert isinstance(provider, OpenAIEmbeddingProvider)
    assert provider.provider_name == "openai"
    assert provider.model_name == "text-embedding-3-small"
    assert provider.dimensions == 384


def test_openai_embedding_provider_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValidationError, match="OPENAI_API_KEY is required"):
        RagSettings(
            _env_file=None,
            backend=RagBackend.PGVECTOR,
            embedding_provider=RagEmbeddingProvider.OPENAI,
            model_name="text-embedding-3-small",
        )


def test_unsupported_embedding_provider_is_rejected() -> None:
    with pytest.raises(ValidationError, match="embedding_provider"):
        RagSettings(
            _env_file=None,
            embedding_provider="unsupported",
        )


def test_openai_provider_rejects_sentence_transformers_model_name() -> None:
    with pytest.raises(ValidationError, match="must be 'text-embedding-3-small'"):
        RagSettings(
            _env_file=None,
            embedding_provider=RagEmbeddingProvider.OPENAI,
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            OPENAI_API_KEY="test-key",
        )


def test_openai_provider_rejects_arbitrary_model_name() -> None:
    with pytest.raises(ValidationError, match="must be 'text-embedding-3-small'"):
        RagSettings(
            _env_file=None,
            embedding_provider=RagEmbeddingProvider.OPENAI,
            model_name="custom-embedding-model",
            OPENAI_API_KEY="test-key",
        )


def test_sentence_transformers_provider_rejects_openai_model_name() -> None:
    with pytest.raises(ValidationError, match="all-MiniLM-L6-v2"):
        RagSettings(
            _env_file=None,
            embedding_provider=RagEmbeddingProvider.SENTENCE_TRANSFORMERS,
            model_name="text-embedding-3-small",
        )


def test_pgvector_dimensions_must_match_current_schema() -> None:
    with pytest.raises(ValidationError, match="vector\\(384\\)"):
        RagSettings(
            _env_file=None,
            backend=RagBackend.PGVECTOR,
            embedding_dimensions=1536,
        )


def test_importing_openai_embedding_path_does_not_import_sentence_transformers() -> None:
    sys.modules.pop("sentence_transformers", None)
    embeddings = importlib.import_module("backend.rag.embeddings")

    assert embeddings.OpenAIEmbeddingProvider
    assert "sentence_transformers" not in sys.modules


def test_fastapi_openai_startup_does_not_import_local_embedding_dependencies() -> None:
    env = {
        **os.environ,
        "RAG_BACKEND": "pgvector",
        "RAG_EMBEDDING_PROVIDER": "openai",
        "RAG_MODEL_NAME": "text-embedding-3-small",
        "RAG_EMBEDDING_DIMENSIONS": "384",
        "OPENAI_API_KEY": "test-key",
    }
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import backend.main; "
                "assert 'sentence_transformers' not in sys.modules; "
                "assert 'torch' not in sys.modules"
            ),
        ],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
