DEFAULT_RAG_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_RAG_EMBEDDING_DIMENSIONS = 384
DEFAULT_RAG_TOP_K = 5
DEFAULT_RAG_CANDIDATE_POOL_MULTIPLIER = 3
DEFAULT_RAG_MAX_CANDIDATES = 50
DEFAULT_CHROMA_PERSIST_PATH = "data/vector_store/chroma"
DEFAULT_CHROMA_COLLECTION_NAME = "capilearn_course_chunks"


def validate_pgvector_model_name(model_name: str) -> str:
    if model_name != DEFAULT_RAG_MODEL_NAME:
        raise ValueError(
            "The pgvector RAG backend requires "
            f"RAG_MODEL_NAME={DEFAULT_RAG_MODEL_NAME!r} because the database schema "
            f"stores {DEFAULT_RAG_EMBEDDING_DIMENSIONS}-dimensional embeddings."
        )
    return model_name
