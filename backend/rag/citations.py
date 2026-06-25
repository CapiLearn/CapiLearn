import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

from markdown_it import MarkdownIt
from markdown_it.token import Token

from backend.core.citations import CitationRecord
from backend.rag.schemas import RetrievedChunk

MAX_CITATION_CHUNK_TEXT_LENGTH = 2000
CITATION_MARKER_PATTERN = re.compile(r"\[([1-9]\d*)\]")
LEGACY_CITATION_LINK_PATTERN = re.compile(r"\[([^\]\n]+)\]\(citation:([^)]+)\)")
INLINE_CITATION_LINK_PATTERN = re.compile(r"(?<!!)\[([1-9]\d*)\]\([^)\n]*\)")
REFERENCE_CITATION_LINK_PATTERN = re.compile(r"(?<!!)\[([1-9]\d*)\]\[([^\]\n]*)\]")
NUMERIC_REFERENCE_DEFINITION_PATTERN = re.compile(
    r"(?m)^[ \t]{0,3}\[([1-9]\d*)\]:[^\n]*(?:\n[ \t]+[^\n]*)*(?:\n|$)"
)
FENCED_CODE_BLOCK_PATTERN = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_PATTERN = re.compile(r"`[^`\n]*`")
MARKDOWN_PARSER = MarkdownIt("commonmark")


@dataclass(frozen=True)
class CitationContext:
    citation_id: str
    source_path: str | None
    heading: str | None
    content: str
    chunk_text: str


@dataclass(frozen=True)
class ValidatedCitations:
    content: str
    citations: list[CitationRecord]


def build_citation_contexts(chunks: list[RetrievedChunk]) -> list[CitationContext]:
    contexts = []
    for rank, chunk in enumerate(chunks, start=1):
        metadata = chunk.metadata or {}
        contexts.append(
            CitationContext(
                citation_id=str(rank),
                source_path=citation_source_path(metadata),
                heading=citation_heading(metadata),
                content=chunk.content,
                chunk_text=citation_chunk_text(chunk.content),
            )
        )
    return contexts


def build_citation_records(chunks: list[RetrievedChunk]) -> list[CitationRecord]:
    return [
        CitationRecord(
            citation_id=context.citation_id,
            source_path=context.source_path,
            heading=context.heading,
            chunk_text=context.chunk_text,
        )
        for context in build_citation_contexts(chunks)
    ]


def validate_cited_response(content: str, chunks: list[RetrievedChunk]) -> ValidatedCitations:
    records = build_citation_records(chunks)
    records_by_id = {record.citation_id: record for record in records}
    normalized_content = normalize_legacy_citation_links(content, set(records_by_id))
    citation_ids = extract_valid_citation_ids(normalized_content, set(records_by_id))

    return ValidatedCitations(
        content=normalized_content,
        citations=[records_by_id[citation_id] for citation_id in citation_ids],
    )


def normalize_legacy_citation_links(content: str, valid_citation_ids: set[str]) -> str:
    def replace_link(match: re.Match[str]) -> str:
        label = match.group(1).strip()
        citation_id = unquote(match.group(2)).strip()

        if citation_id in valid_citation_ids and label == citation_id:
            return f"[{citation_id}]"

        return f"[{label}]"

    normalized_content = _sub_outside_code(content, LEGACY_CITATION_LINK_PATTERN, replace_link)
    normalized_content = _sub_outside_code(
        normalized_content,
        INLINE_CITATION_LINK_PATTERN,
        lambda match: f"[{match.group(1)}]",
    )

    reference_labels = _reference_labels(normalized_content)

    def replace_reference_link(match: re.Match[str]) -> str:
        citation_id = match.group(1)
        reference_label = match.group(2).strip() or citation_id
        if _normalize_reference_label(reference_label) in reference_labels:
            return f"[{citation_id}]"
        return match.group(0)

    normalized_content = _sub_outside_code(
        normalized_content,
        REFERENCE_CITATION_LINK_PATTERN,
        replace_reference_link,
    )
    return _sub_outside_code(
        normalized_content,
        NUMERIC_REFERENCE_DEFINITION_PATTERN,
        lambda match: "",
    )


def extract_valid_citation_ids(content: str, valid_citation_ids: set[str]) -> list[str]:
    citation_ids = []
    seen_ids = set()

    for text in _iter_citable_markdown_text(content):
        for match in CITATION_MARKER_PATTERN.finditer(text):
            citation_id = match.group(1)
            if citation_id not in valid_citation_ids or citation_id in seen_ids:
                continue

            citation_ids.append(citation_id)
            seen_ids.add(citation_id)

    return citation_ids


def citation_source_path(metadata: dict[str, Any]) -> str | None:
    source_path = _optional_string(_metadata_value(metadata, "source_path", "sourcePath"))
    if source_path is None:
        return None

    return _source_file_name(source_path)


def citation_heading(metadata: dict[str, Any]) -> str | None:
    heading_path = _metadata_value(metadata, "heading_path", "headingPath")
    if isinstance(heading_path, str):
        heading = heading_path.strip()
    elif isinstance(heading_path, list | tuple):
        heading = " > ".join(str(part).strip() for part in heading_path if str(part).strip())
    else:
        heading = ""

    if heading:
        return heading

    return _optional_string(_metadata_value(metadata, "section_heading", "sectionHeading"))


def citation_chunk_text(content: str) -> str:
    if len(content) <= MAX_CITATION_CHUNK_TEXT_LENGTH:
        return content
    return f"{content[:MAX_CITATION_CHUNK_TEXT_LENGTH]}..."


def _metadata_value(metadata: dict[str, Any], snake_key: str, camel_key: str) -> Any:
    value = metadata.get(snake_key)
    if value is not None:
        return value
    return metadata.get(camel_key)


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _source_file_name(source_path: str) -> str | None:
    file_name = source_path.replace("\\", "/").rstrip("/").rsplit("/", maxsplit=1)[-1].strip()
    return file_name or None


def _mask_code_spans(content: str) -> str:
    masked_content = FENCED_CODE_BLOCK_PATTERN.sub(_same_length_spaces, content)
    return INLINE_CODE_PATTERN.sub(_same_length_spaces, masked_content)


def _iter_citable_markdown_text(content: str) -> Iterable[str]:
    for token in MARKDOWN_PARSER.parse(content):
        if token.type == "inline" and token.children is not None:
            yield from _iter_citable_inline_text(token.children)


def _iter_citable_inline_text(tokens: Iterable[Token]) -> Iterable[str]:
    token_list = list(tokens)
    index = 0

    while index < len(token_list):
        token = token_list[index]
        if token.type == "link_open":
            link_text, link_close_index = _link_text(token_list, index)
            if link_text.isdecimal():
                yield f"[{link_text}]"
            index = link_close_index + 1
            continue
        if token.type == "link_close":
            index += 1
            continue
        if token.type in {"code_inline", "image"}:
            index += 1
            continue
        if token.type == "text":
            yield token.content
        index += 1


def _link_text(tokens: list[Token], link_open_index: int) -> tuple[str, int]:
    text_parts = []
    nesting = 0
    index = link_open_index

    while index < len(tokens):
        token = tokens[index]
        if token.type == "link_open":
            nesting += 1
        elif token.type == "link_close":
            nesting -= 1
            if nesting == 0:
                return "".join(text_parts), index
        elif nesting == 1 and token.type == "text":
            text_parts.append(token.content)

        index += 1

    return "", link_open_index


def _sub_outside_code(
    content: str,
    pattern: re.Pattern[str],
    replace: Callable[[re.Match[str]], str],
) -> str:
    masked_content = _mask_code_spans(content)
    normalized_parts = []
    last_index = 0

    for match in pattern.finditer(content):
        if _is_masked(masked_content, match.start()):
            continue

        normalized_parts.append(content[last_index : match.start()])
        normalized_parts.append(replace(match))
        last_index = match.end()

    if not normalized_parts:
        return content

    normalized_parts.append(content[last_index:])
    return "".join(normalized_parts)


def _reference_labels(content: str) -> set[str]:
    env: dict[str, Any] = {}
    MARKDOWN_PARSER.parse(content, env)
    return set(env.get("references", {}))


def _normalize_reference_label(label: str) -> str:
    return " ".join(label.split()).upper()


def _same_length_spaces(match: re.Match[str]) -> str:
    return " " * len(match.group(0))


def _is_masked(masked_content: str, index: int) -> bool:
    return index < len(masked_content) and masked_content[index] == " "
