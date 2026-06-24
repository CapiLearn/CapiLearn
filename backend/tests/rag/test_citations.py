import pytest
from pydantic import ValidationError

from backend.core.citations import CitationRecord
from backend.rag.citations import (
    MAX_CITATION_CHUNK_TEXT_LENGTH,
    build_citation_records,
    extract_valid_citation_ids,
    validate_cited_response,
)
from backend.rag.schemas import RetrievedChunk


def test_citation_records_normalize_metadata_and_chunk_text() -> None:
    chunk = RetrievedChunk(
        content="State belongs to a component.",
        metadata={
            "chunk_id": "018f7fd2-0f4d-7b62-a542-c1b937dc7468",
            "source_path": "src/content/1/en/part1.md",
            "heading_path": ["State", "Updating state"],
            "chunk_type": "prose",
        },
    )

    record = build_citation_records([chunk])[0]

    assert record.citation_id == "1"
    assert record.source_path == "part1.md"
    assert record.heading == "State > Updating state"
    assert record.chunk_text == "State belongs to a component."
    assert not hasattr(record, "chunk_id")
    assert not hasattr(record, "retrieval_rank")
    assert not hasattr(record, "chunk_type")
    assert not hasattr(record, "content")
    assert not hasattr(record, "label")


def test_citation_records_use_sequential_citation_ids() -> None:
    records = build_citation_records(
        [
            RetrievedChunk(
                content="State belongs to a component.",
                metadata={
                    "source_path": "state.md",
                    "section_heading": "State",
                    "chunk_type": "prose",
                },
            ),
            RetrievedChunk(
                content="Setters schedule updates.",
                metadata={
                    "source_path": "setters.md",
                    "section_heading": "Setters",
                    "chunk_type": "code",
                },
            ),
        ]
    )

    assert [record.citation_id for record in records] == ["1", "2"]
    assert [record.model_dump(mode="json", by_alias=True) for record in records] == [
        {
            "citationId": "1",
            "sourcePath": "state.md",
            "heading": "State",
            "chunkText": "State belongs to a component.",
        },
        {
            "citationId": "2",
            "sourcePath": "setters.md",
            "heading": "Setters",
            "chunkText": "Setters schedule updates.",
        },
    ]
    assert not hasattr(records[0], "chunk_type")


@pytest.mark.parametrize("citation_id", ["", " ", " 1", "1 ", "abc", "0", "01", 1])
def test_citation_records_reject_noncanonical_citation_ids(citation_id) -> None:
    with pytest.raises(ValidationError):
        CitationRecord(citation_id=citation_id, chunk_text="Source text")


def test_citation_record_requires_builder_owned_fields() -> None:
    with pytest.raises(ValidationError):
        CitationRecord(chunk_text="Source text")

    with pytest.raises(ValidationError):
        CitationRecord(citation_id="123456")


def test_citation_record_allows_nullable_display_metadata() -> None:
    payload = CitationRecord(
        citation_id="123456",
        source_path=None,
        heading=None,
        chunk_text="Source text",
    )

    assert payload.citation_id == "123456"
    assert payload.source_path is None
    assert payload.heading is None
    assert payload.chunk_text == "Source text"


def test_citation_record_rejects_camel_case_internal_construction() -> None:
    with pytest.raises(ValidationError):
        CitationRecord(
            citationId="123456",
            sourcePath="state.md",
            heading="State",
            chunkText="Source text",
        )


def test_citation_records_strip_source_directories_from_display_metadata() -> None:
    records = build_citation_records(
        [
            RetrievedChunk(
                content="Unix path",
                metadata={"source_path": "src/content/6/en/part6d.md"},
            ),
            RetrievedChunk(
                content="Windows path",
                metadata={"sourcePath": r"src\content\7\en\part7a.md"},
            ),
        ]
    )

    assert [record.source_path for record in records] == ["part6d.md", "part7a.md"]


def test_citation_records_cap_persisted_chunk_text() -> None:
    content = "x" * (MAX_CITATION_CHUNK_TEXT_LENGTH + 10)

    record = build_citation_records([RetrievedChunk(content=content)])[0]

    assert record.chunk_text == f"{content[:MAX_CITATION_CHUNK_TEXT_LENGTH]}..."


def test_citation_records_return_persisted_shape_directly() -> None:
    record = build_citation_records(
        [
            RetrievedChunk(
                content="State belongs to a component.",
                metadata={"source_path": "state.md"},
            )
        ]
    )[0]

    assert record.model_dump(mode="json", by_alias=True) == {
        "citationId": "1",
        "sourcePath": "state.md",
        "heading": None,
        "chunkText": "State belongs to a component.",
    }
    assert not hasattr(record, "chunk_id")
    assert not hasattr(record, "retrieval_rank")
    assert not hasattr(record, "chunk_type")
    assert not hasattr(record, "content")
    assert not hasattr(record, "label")


def test_citation_records_validate_wire_shape() -> None:
    payload = CitationRecord.model_validate_wire(
        {
            "citationId": "1",
            "sourcePath": "state.md",
            "heading": "State",
            "chunkText": "Source text",
        }
    )

    assert payload.citation_id == "1"
    assert payload.source_path == "state.md"
    assert payload.heading == "State"
    assert payload.chunk_text == "Source text"


def test_citation_records_reject_snake_case_wire_shape() -> None:
    with pytest.raises(ValidationError):
        CitationRecord.model_validate_wire(
            {
                "citation_id": "1",
                "source_path": "state.md",
                "heading": "State",
                "chunk_text": "Source text",
            }
        )


def test_citation_records_reject_legacy_persisted_metadata() -> None:
    with pytest.raises(ValidationError):
        CitationRecord.model_validate_wire(
            {
                "citationId": "1",
                "sourcePath": "state.md",
                "heading": "State",
                "chunkText": "Source text",
                "chunkId": "018f7fd2-0f4d-7b62-a542-c1b937dc7468",
                "retrievalRank": 1,
                "chunkType": "prose",
            }
        )


def test_citation_records_allow_missing_display_metadata() -> None:
    records = build_citation_records([RetrievedChunk(content="State belongs to a component.")])

    assert records[0].model_dump(mode="json", by_alias=True) == {
        "citationId": "1",
        "sourcePath": None,
        "heading": None,
        "chunkText": "State belongs to a component.",
    }


def test_validate_cited_response_keeps_only_used_citations_in_text_order() -> None:
    result = validate_cited_response(
        "Second source first [2]. Then first source [1]. Repeated second source [2].",
        [
            RetrievedChunk(content="First context", metadata={"source_path": "first.md"}),
            RetrievedChunk(content="Second context", metadata={"source_path": "second.md"}),
            RetrievedChunk(content="Unused context", metadata={"source_path": "unused.md"}),
        ],
    )

    assert result.content == (
        "Second source first [2]. Then first source [1]. Repeated second source [2]."
    )
    assert [citation.citation_id for citation in result.citations] == ["2", "1"]
    assert [citation.source_path for citation in result.citations] == [
        "second.md",
        "first.md",
    ]


def test_validate_cited_response_ignores_invalid_and_uncited_markers() -> None:
    result = validate_cited_response(
        "Known [1]. Invalid [9].",
        [RetrievedChunk(content="Known context")],
    )

    assert result.content == "Known [1]. Invalid [9]."
    assert [citation.citation_id for citation in result.citations] == ["1"]


def test_extract_valid_citation_ids_ignores_code_and_markdown_links() -> None:
    content = "Cite [1]. Ignore `[2]` and ```\n[3]\n```. Also ignore [4](https://example.com)."

    assert extract_valid_citation_ids(content, {"1", "2", "3", "4"}) == ["1"]


def test_validate_cited_response_normalizes_legacy_citation_links() -> None:
    result = validate_cited_response(
        "Legacy markdown citation [1](citation:1).",
        [RetrievedChunk(content="Known context")],
    )

    assert result.content == "Legacy markdown citation [1]."
    assert [citation.citation_id for citation in result.citations] == ["1"]


def test_validate_cited_response_does_not_normalize_legacy_links_inside_code() -> None:
    result = validate_cited_response(
        "Code example `[1](citation:1)` stays literal.",
        [RetrievedChunk(content="Known context")],
    )

    assert result.content == "Code example `[1](citation:1)` stays literal."
    assert result.citations == []
