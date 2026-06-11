DEFAULT_RAG_EMBEDDING_PROVIDER = "sentence_transformers"
DEFAULT_RAG_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_RAG_EMBEDDING_DIMENSIONS = 384
DEFAULT_RAG_TOP_K = 5
DEPLOYED_RAG_EMBEDDING_PROVIDER = "openai"
DEPLOYED_RAG_MODEL_NAME = "text-embedding-3-small"
DEFAULT_CHROMA_PERSIST_PATH = "data/vector_store/chroma"
DEFAULT_CHROMA_COLLECTION_NAME = "capilearn_course_chunks"


def validate_pgvector_dimensions(dimensions: int) -> int:
    if dimensions != DEFAULT_RAG_EMBEDDING_DIMENSIONS:
        raise ValueError(
            "The pgvector RAG backend requires "
            f"RAG_EMBEDDING_DIMENSIONS={DEFAULT_RAG_EMBEDDING_DIMENSIONS} because "
            "the current database schema stores vector(384) embeddings."
        )
    return dimensions
