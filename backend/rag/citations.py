import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

from backend.core.citations import CitationRecord
from backend.rag.schemas import RetrievedChunk

MAX_CITATION_CHUNK_TEXT_LENGTH = 2000
PLAIN_CITATION_MARKER_PATTERN = re.compile(r"(?<!!)\[(\d+)\](?!\()")
LEGACY_CITATION_LINK_PATTERN = re.compile(r"\[([^\]\n]+)\]\(citation:([^)]+)\)")
FENCED_CODE_BLOCK_PATTERN = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_PATTERN = re.compile(r"`[^`\n]*`")


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
    masked_content = _mask_code_spans(content)
    normalized_parts = []
    last_index = 0

    def replace_link(match: re.Match[str]) -> str:
        label = match.group(1).strip()
        citation_id = unquote(match.group(2)).strip()

        if citation_id in valid_citation_ids and label == citation_id:
            return f"[{citation_id}]"

        return f"[{label}]"

    for match in LEGACY_CITATION_LINK_PATTERN.finditer(content):
        if _is_masked(masked_content, match.start()):
            continue

        normalized_parts.append(content[last_index : match.start()])
        normalized_parts.append(replace_link(match))
        last_index = match.end()

    if not normalized_parts:
        return content

    normalized_parts.append(content[last_index:])
    return "".join(normalized_parts)


def extract_valid_citation_ids(content: str, valid_citation_ids: set[str]) -> list[str]:
    masked_content = _mask_code_spans(content)
    citation_ids = []
    seen_ids = set()

    for match in PLAIN_CITATION_MARKER_PATTERN.finditer(masked_content):
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


def _same_length_spaces(match: re.Match[str]) -> str:
    return " " * len(match.group(0))


def _is_masked(masked_content: str, index: int) -> bool:
    return index < len(masked_content) and masked_content[index] == " "
