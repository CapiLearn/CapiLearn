from backend.llm.prompts import build_context_block
from backend.rag.schemas import RetrievedChunk


def test_context_label_includes_path_heading_and_useful_type() -> None:
    context = build_context_block(
        [
            RetrievedChunk(
                content="const state = value",
                metadata={
                    "source_path": "src/content/1/en/part1.md",
                    "heading_path": ["State", "Updating state"],
                    "chunk_type": "code",
                },
            )
        ]
    )

    assert context.startswith("[1] src/content/1/en/part1.md | State > Updating state | code\n")
    assert len(context.splitlines()[0]) < 100


def test_context_label_uses_section_heading_and_omits_plain_prose_type() -> None:
    context = build_context_block(
        [
            RetrievedChunk(
                content="State belongs to a component.",
                metadata={
                    "source_path": "state.md",
                    "section_heading": "State",
                    "chunk_type": "prose",
                },
            )
        ]
    )

    assert context.startswith("[1] state.md | State\n")


def test_context_label_degrades_gracefully_without_metadata() -> None:
    context = build_context_block([RetrievedChunk(content="Context")])

    assert context == "[1]\nContext"
