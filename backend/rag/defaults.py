DEFAULT_RAG_EMBEDDING_PROVIDER = "openai"
DEFAULT_RAG_MODEL_NAME = "text-embedding-3-small"
DEFAULT_RAG_EMBEDDING_DIMENSIONS = 384
DEFAULT_RAG_TOP_K = 5
DEFAULT_RAG_CANDIDATE_POOL_MULTIPLIER = 3
DEFAULT_RAG_MAX_CANDIDATES = 50


def validate_pgvector_embedding_contract(
    *,
    embedding_provider: str,
    model_name: str,
    embedding_dimensions: int,
) -> tuple[str, str, int]:
    if embedding_provider != DEFAULT_RAG_EMBEDDING_PROVIDER:
        raise ValueError(
            "The pgvector RAG backend requires "
            f"RAG_EMBEDDING_PROVIDER={DEFAULT_RAG_EMBEDDING_PROVIDER!r}; "
            "local embedding fallback is not supported."
        )
    if model_name != DEFAULT_RAG_MODEL_NAME:
        raise ValueError(
            "The pgvector RAG backend requires "
            f"RAG_MODEL_NAME={DEFAULT_RAG_MODEL_NAME!r} because the database schema "
            f"stores {DEFAULT_RAG_EMBEDDING_DIMENSIONS}-dimensional embeddings."
        )
    if embedding_dimensions != DEFAULT_RAG_EMBEDDING_DIMENSIONS:
        raise ValueError(
            "The pgvector RAG backend requires "
            f"RAG_EMBEDDING_DIMENSIONS={DEFAULT_RAG_EMBEDDING_DIMENSIONS}."
        )
    return embedding_provider, model_name, embedding_dimensions


def validate_pgvector_model_name(model_name: str) -> str:
    validate_pgvector_embedding_contract(
        embedding_provider=DEFAULT_RAG_EMBEDDING_PROVIDER,
        model_name=model_name,
        embedding_dimensions=DEFAULT_RAG_EMBEDDING_DIMENSIONS,
    )
    return model_name
