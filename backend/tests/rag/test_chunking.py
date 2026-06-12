from uuid import UUID

from backend.rag.chunk_identity import content_hash
from backend.rag.chunking import CHUNKER_VERSION, SourceDocument, prepare_chunks


def _document(
    content: str,
    *,
    source_path: str = "src/content/1/en/state.md",
) -> SourceDocument:
    return SourceDocument(
        content=content,
        source_type="course_repo",
        source_path=source_path,
        document_id=source_path,
        metadata={"file_name": "state.md"},
    )


def test_identical_source_produces_identical_deterministic_chunk_ids() -> None:
    document = _document("# State\n\nCourse content")

    first = prepare_chunks(document, chunk_size=1000, overlap=200)
    second = prepare_chunks(document, chunk_size=1000, overlap=200)

    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
    assert all(chunk.chunk_id.version == 5 for chunk in first)


def test_different_source_paths_do_not_collide_for_identical_content() -> None:
    first = prepare_chunks(
        _document("Same content", source_path="one.md"),
        chunk_size=100,
        overlap=10,
    )
    second = prepare_chunks(
        _document("Same content", source_path="two.md"),
        chunk_size=100,
        overlap=10,
    )

    assert first[0].chunk_id != second[0].chunk_id


def test_repeated_identical_chunks_get_distinct_deterministic_ids() -> None:
    document = _document("# Same\n\nText\n\n# Same\n\nText")

    first = prepare_chunks(document, chunk_size=100, overlap=10)
    second = prepare_chunks(document, chunk_size=100, overlap=10)

    assert first[0].content == first[1].content
    assert first[0].content_hash == first[1].content_hash
    assert first[0].chunk_id != first[1].chunk_id
    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]


def test_content_hash_changes_with_chunk_content() -> None:
    original = prepare_chunks(_document("Original"), chunk_size=100, overlap=10)[0]
    changed = prepare_chunks(_document("Changed"), chunk_size=100, overlap=10)[0]

    assert original.content_hash == content_hash("Original")
    assert changed.content_hash == content_hash("Changed")
    assert original.content_hash != changed.content_hash


def test_heading_metadata_and_offsets_are_populated() -> None:
    source = "# Part 1\n\nIntro\n\n## State\n\nState content"
    chunks = prepare_chunks(_document(source), chunk_size=1000, overlap=200)

    state_chunk = chunks[1]
    assert state_chunk.chunk_index == 1
    assert state_chunk.chunker_version == CHUNKER_VERSION
    assert state_chunk.heading_path == ("Part 1", "State")
    assert state_chunk.section_heading == "State"
    assert state_chunk.chunk_type == "prose"
    assert state_chunk.content_hash
    assert state_chunk.char_start is not None
    assert state_chunk.char_end is not None
    assert source[state_chunk.char_start : state_chunk.char_end] == state_chunk.content


def test_offsets_are_half_open_and_map_to_source_content() -> None:
    source = "# State\n\n" + ("First sentence. " * 80)
    chunks = prepare_chunks(_document(source), chunk_size=1000, overlap=200)

    assert len(chunks) == 2
    for chunk in chunks:
        assert isinstance(chunk.chunk_id, UUID)
        assert chunk.char_start is not None
        assert chunk.char_end is not None
        assert chunk.char_start < chunk.char_end
        assert source[chunk.char_start : chunk.char_end] == chunk.content


def test_nested_headings_and_continuations_retain_heading_path() -> None:
    source = "# Course\n\n## React\n\n" + ("State updates components. " * 30)

    chunks = prepare_chunks(_document(source), chunk_size=180, overlap=20)

    react_chunks = [chunk for chunk in chunks if chunk.section_heading == "React"]
    assert len(react_chunks) > 1
    assert all(chunk.heading_path == ("Course", "React") for chunk in react_chunks)


def test_heading_inside_fenced_code_is_ignored() -> None:
    source = "# Real\n\n```python\n## Fake heading\nprint('ok')\n```\n\n## Next\n\nText"

    chunks = prepare_chunks(_document(source), chunk_size=200, overlap=20)

    assert ("Real", "Fake heading") not in [chunk.heading_path for chunk in chunks]
    assert any(chunk.heading_path == ("Real", "Next") for chunk in chunks)


def test_complete_backtick_fence_and_info_string_remain_intact() -> None:
    source = "```python\nprint('hello')\n```"

    chunks = prepare_chunks(_document(source), chunk_size=100, overlap=10)

    assert len(chunks) == 1
    assert chunks[0].content == source
    assert chunks[0].chunk_type == "code"
    assert chunks[0].metadata["fence_info"] == "python"
    assert _fences_are_balanced(chunks[0].content, "`")


def test_tilde_fence_remains_intact() -> None:
    source = "~~~js\nconsole.log('hello')\n~~~"

    chunks = prepare_chunks(_document(source), chunk_size=100, overlap=10)

    assert len(chunks) == 1
    assert chunks[0].content == source
    assert chunks[0].metadata["fence_info"] == "js"
    assert _fences_are_balanced(chunks[0].content, "~")


def test_unclosed_fence_is_closed_safely_and_records_diagnostics() -> None:
    source = "```python\nprint('hello')"

    chunk = prepare_chunks(_document(source), chunk_size=100, overlap=10)[0]

    assert chunk.content.endswith("\n```")
    assert chunk.metadata["malformed_fence"] is True
    assert chunk.metadata["synthetic_closing_fence"] is True
    assert chunk.metadata["rendered_content_differs"] is True
    assert chunk.char_start == 0
    assert chunk.char_end == len(source)
    assert _fences_are_balanced(chunk.content, "`")


def test_oversized_code_uses_explicit_policy() -> None:
    source = "```python\n" + "".join(f"print({index})\n" for index in range(40)) + "```"

    chunks = prepare_chunks(
        _document(source),
        chunk_size=100,
        overlap=10,
        max_oversized_code_chars=160,
    )

    assert len(chunks) > 1
    assert all(chunk.chunk_type == "code" for chunk in chunks)
    assert all(chunk.metadata["oversized_code"] is True for chunk in chunks)
    assert all(chunk.metadata["synthetic_opening_fence"] is True for chunk in chunks)
    assert all(_fences_are_balanced(chunk.content, "`") for chunk in chunks)
    assert all(len(chunk.content) <= 100 for chunk in chunks)


def test_complete_code_can_exceed_preferred_size_up_to_hard_maximum() -> None:
    source = "```\n" + ("x = 1\n" * 20) + "```"

    chunks = prepare_chunks(
        _document(source),
        chunk_size=80,
        overlap=10,
        max_oversized_code_chars=200,
    )

    assert len(chunks) == 1
    assert len(chunks[0].content) > 80
    assert chunks[0].metadata["allowed_oversized_code"] is True
    assert _fences_are_balanced(chunks[0].content, "`")


def test_long_prose_splits_at_paragraph_boundaries_before_fallback() -> None:
    first = "First paragraph sentence. " * 5
    second = "Second paragraph sentence. " * 5
    source = f"# Topic\n\n{first}\n\n{second}"

    chunks = prepare_chunks(_document(source), chunk_size=150, overlap=10)

    assert len(chunks) == 2
    assert chunks[0].content.endswith(first.strip())
    assert chunks[1].content == second.strip()
    assert all(chunk.metadata.get("split_reason") != "character_fallback" for chunk in chunks)


def test_markdown_list_stays_coherent_and_is_classified() -> None:
    source = "- first item\n- second item\n- third item"

    chunks = prepare_chunks(_document(source), chunk_size=100, overlap=10)

    assert len(chunks) == 1
    assert chunks[0].content == source
    assert chunks[0].chunk_type == "list"


def test_markdown_table_is_classified_and_split_with_repeated_header() -> None:
    source = (
        "| Name | Value |\n"
        "| --- | --- |\n"
        "| alpha | one |\n"
        "| beta | two |\n"
        "| gamma | three |\n"
        "| delta | four |"
    )

    chunks = prepare_chunks(_document(source), chunk_size=65, overlap=10)

    assert len(chunks) > 1
    assert all(chunk.chunk_type == "table" for chunk in chunks)
    assert all(chunk.content.startswith("| Name | Value |\n| --- | --- |") for chunk in chunks)
    assert all(chunk.metadata["synthetic_table_header"] is True for chunk in chunks)


def test_character_fallback_is_used_only_for_unbreakable_text() -> None:
    source = "A" * 250

    chunks = prepare_chunks(_document(source), chunk_size=100, overlap=20)

    assert len(chunks) == 3
    assert all(chunk.metadata["split_reason"] == "character_fallback" for chunk in chunks)
    assert all(len(chunk.content) <= 100 for chunk in chunks)


def test_tiny_prose_merges_with_compatible_neighbor() -> None:
    source = "- first item\n- second item\n\nBrief note."

    chunks = prepare_chunks(
        _document(source),
        chunk_size=100,
        overlap=10,
        min_chunk_chars=20,
    )

    assert len(chunks) == 1
    assert chunks[0].chunk_type == "mixed"
    assert chunks[0].metadata["tiny_chunk_merged"] is True


def test_tiny_code_and_table_chunks_are_preserved() -> None:
    source = "```\nx\n```\n\n| A | B |\n| --- | --- |\n| 1 | 2 |"

    chunks = prepare_chunks(
        _document(source),
        chunk_size=100,
        overlap=10,
        min_chunk_chars=80,
    )

    assert [chunk.chunk_type for chunk in chunks] == ["code", "table"]


def test_tiny_chunk_does_not_merge_across_top_level_sections() -> None:
    source = "# One\n\nShort.\n\n# Two\n\nAlso short."

    chunks = prepare_chunks(
        _document(source),
        chunk_size=100,
        overlap=10,
        min_chunk_chars=80,
    )

    assert len(chunks) == 2
    assert [chunk.heading_path for chunk in chunks] == [("One",), ("Two",)]


def test_repeated_heading_names_in_different_sections_remain_distinct() -> None:
    source = "# First\n\n## Setup\n\nText\n\n# Second\n\n## Setup\n\nText"

    chunks = prepare_chunks(_document(source), chunk_size=100, overlap=10)
    setup_chunks = [chunk for chunk in chunks if chunk.section_heading == "Setup"]

    assert len(setup_chunks) == 2
    assert setup_chunks[0].heading_path == ("First", "Setup")
    assert setup_chunks[1].heading_path == ("Second", "Setup")
    assert setup_chunks[0].chunk_id != setup_chunks[1].chunk_id


def test_regression_markdown_never_emits_broken_normal_fences() -> None:
    source = (
        "# Example\n\n"
        "Intro paragraph.\n\n"
        "```python\n" + ("print('a fairly long line')\n" * 10) + "```\n\n"
        "Closing paragraph."
    )

    chunks = prepare_chunks(_document(source), chunk_size=120, overlap=20)

    fenced_chunks = [chunk for chunk in chunks if "```" in chunk.content]
    assert fenced_chunks
    assert all(_fences_are_balanced(chunk.content, "`") for chunk in fenced_chunks)


def _fences_are_balanced(content: str, marker: str) -> bool:
    fence_lines = [line for line in content.splitlines() if line.lstrip().startswith(marker * 3)]
    return len(fence_lines) % 2 == 0
