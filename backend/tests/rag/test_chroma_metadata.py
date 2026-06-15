import json

import pytest

from backend.rag.build_chroma_vector_store import build_chroma_vector_store, clean_metadata


def test_clean_metadata_flattens_typed_chunk_metadata_for_chroma() -> None:
    metadata = clean_metadata(
        {
            "document_id": "state.md",
            "chunk_index": 2,
            "metadata": {
                "source_path": "src/content/1/en/state.md",
                "heading_path": ["Part 1", "State"],
                "section_heading": "State",
                "chunk_type": "unknown",
                "content_hash": "abc123",
                "chunker_version": "markdown-window-v2-contract",
                "char_start": 10,
                "char_end": 30,
            },
        }
    )

    assert metadata["heading_path"] == "Part 1 > State"
    assert metadata["content_hash"] == "abc123"
    assert metadata["chunker_version"] == "markdown-window-v2-contract"
    assert metadata["char_start"] == 10
    assert metadata["char_end"] == 30


def test_chroma_empty_rebuild_fails_instead_of_leaving_stale_index(tmp_path) -> None:
    chunks_path = tmp_path / "chunks.json"
    chunks_path.write_text(json.dumps([{"content": "   "}]), encoding="utf-8")

    with pytest.raises(ValueError, match="refusing to leave an existing Chroma collection"):
        build_chroma_vector_store(
            chunks_path=str(chunks_path),
            persist_path=str(tmp_path / "chroma"),
            collection_name="test",
            model_name="unused",
        )
