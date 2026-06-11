from uuid import uuid4

from backend.rag.deduplication import deduplicate_chunks
from backend.rag.schemas import RetrievedChunk


def _chunk(content: str, **metadata) -> RetrievedChunk:
    return RetrievedChunk(content=content, metadata=metadata)


def test_deduplicates_exact_content_hash() -> None:
    result = deduplicate_chunks(
        [
            _chunk("First", chunk_id=str(uuid4()), content_hash="same"),
            _chunk("Second", chunk_id=str(uuid4()), content_hash="same"),
        ],
        top_k=5,
    )

    assert [chunk.content for chunk in result.chunks] == ["First"]
    assert result.suppression_reasons == {"content_hash": 1}


def test_deduplicates_normalized_content_when_hash_is_missing() -> None:
    result = deduplicate_chunks(
        [_chunk("Same   content"), _chunk(" Same content\n")],
        top_k=5,
    )

    assert len(result.chunks) == 1
    assert result.suppression_reasons == {"normalized_content": 1}


def test_deduplicates_highly_overlapping_offsets_in_same_document() -> None:
    document_id = str(uuid4())
    result = deduplicate_chunks(
        [
            _chunk("First", document_id=document_id, char_start=0, char_end=100),
            _chunk("Overlap", document_id=document_id, char_start=10, char_end=90),
        ],
        top_k=5,
    )

    assert [chunk.content for chunk in result.chunks] == ["First"]
    assert result.suppression_reasons == {"overlapping_offsets": 1}


def test_preserves_adjacent_chunks_and_respects_top_k() -> None:
    document_id = str(uuid4())
    candidates = [
        _chunk("One", document_id=document_id, char_start=0, char_end=100),
        _chunk("Two", document_id=document_id, char_start=100, char_end=200),
        _chunk("Three", document_id=document_id, char_start=200, char_end=300),
    ]

    first = deduplicate_chunks(candidates, top_k=2)
    second = deduplicate_chunks(candidates, top_k=2)

    assert [chunk.content for chunk in first.chunks] == ["One", "Two"]
    assert first == second
    assert first.candidate_count == 3
    assert first.suppression_reasons == {}


def test_deduplicates_same_chunk_id() -> None:
    chunk_id = str(uuid4())
    result = deduplicate_chunks(
        [_chunk("One", chunk_id=chunk_id), _chunk("Two", chunk_id=chunk_id)],
        top_k=5,
    )

    assert len(result.chunks) == 1
    assert result.suppression_reasons == {"chunk_id": 1}
