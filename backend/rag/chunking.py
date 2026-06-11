from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from backend.rag.chunk_identity import content_hash, deterministic_chunk_id

CHUNKER_VERSION = "markdown-structure-v3"
DEFAULT_MIN_CHUNK_CHARS = 120
DEFAULT_MAX_OVERSIZED_CODE_CHARS = 4000

_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*(?:\r?\n)?$")
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})([^\r\n]*)(?:\r?\n)?$")
_LIST_RE = re.compile(r"^ {0,3}(?:[-+*]|\d+[.)])[ \t]+")
_TABLE_SEPARATOR_RE = re.compile(
    r"^ {0,3}\|?[ \t]*:?-{3,}:?[ \t]*(?:\|[ \t]*:?-{3,}:?[ \t]*)+\|?[ \t]*$"
)
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])(?:[\"')\]]*)\s+")


@dataclass(frozen=True)
class SourceDocument:
    content: str
    source_type: str
    source_path: str
    document_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChunkDraft:
    content: str
    heading_path: tuple[str, ...]
    section_heading: str | None
    chunk_type: str
    char_start: int | None
    char_end: int | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PreparedChunk:
    chunk_id: UUID
    content: str
    chunk_index: int
    source_type: str
    source_path: str
    heading_path: tuple[str, ...]
    section_heading: str | None
    chunk_type: str
    char_start: int | None
    char_end: int | None
    content_hash: str
    chunker_version: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def persistence_metadata(self) -> dict[str, Any]:
        return {
            **self.metadata,
            "source_type": self.source_type,
            "source_path": self.source_path,
            "heading_path": list(self.heading_path),
            "section_heading": self.section_heading,
            "chunk_type": self.chunk_type,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "content_hash": self.content_hash,
            "chunker_version": self.chunker_version,
        }

    def to_legacy_dict(self, *, document_id: str | None = None) -> dict[str, Any]:
        return {
            "chunk_id": str(self.chunk_id),
            "document_id": document_id,
            "chunk_index": self.chunk_index,
            "content": self.content,
            "metadata": self.persistence_metadata(),
        }


@dataclass(frozen=True)
class _Line:
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class _Block:
    kind: str
    start: int
    end: int
    heading_path: tuple[str, ...]
    section_heading: str | None
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def synthetic(self) -> bool:
        return bool(self.metadata.get("rendered_content_differs"))


def prepare_chunks(
    document: SourceDocument,
    *,
    chunk_size: int,
    overlap: int,
    min_chunk_chars: int = DEFAULT_MIN_CHUNK_CHARS,
    max_oversized_code_chars: int = DEFAULT_MAX_OVERSIZED_CODE_CHARS,
    chunker_version: str = CHUNKER_VERSION,
) -> list[PreparedChunk]:
    _validate_config(
        chunk_size=chunk_size,
        overlap=overlap,
        min_chunk_chars=min_chunk_chars,
        max_oversized_code_chars=max_oversized_code_chars,
    )
    blocks = _parse_markdown_blocks(document.content)
    split_blocks = []
    for block in blocks:
        split_blocks.extend(
            _split_block(
                block,
                chunk_size=chunk_size,
                overlap=overlap,
                max_oversized_code_chars=max_oversized_code_chars,
            )
        )
    drafts = _assemble_chunks(document.content, split_blocks, chunk_size=chunk_size)
    drafts = _merge_tiny_chunks(
        document.content,
        drafts,
        min_chunk_chars=min(min_chunk_chars, chunk_size),
        chunk_size=chunk_size,
    )
    return _finalize_chunks(document, drafts, chunker_version=chunker_version)


def _validate_config(
    *,
    chunk_size: int,
    overlap: int,
    min_chunk_chars: int,
    max_oversized_code_chars: int,
) -> None:
    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be between 0 and chunk_size - 1")
    if min_chunk_chars < 0:
        raise ValueError("min_chunk_chars must be at least 0")
    if max_oversized_code_chars < chunk_size:
        raise ValueError("max_oversized_code_chars must be at least chunk_size")


def _parse_markdown_blocks(text: str) -> list[_Block]:
    lines = _source_lines(text)
    blocks: list[_Block] = []
    heading_levels: dict[int, str] = {}
    section_start = 0
    index = 0

    while index < len(lines):
        line = lines[index]
        if not line.text.strip():
            index += 1
            continue

        fence_match = _FENCE_RE.match(line.text)
        if fence_match:
            block, index = _consume_fence(
                text,
                lines,
                index,
                heading_path=_current_heading_path(heading_levels),
                section_start=section_start,
            )
            blocks.append(block)
            continue

        heading_match = _HEADING_RE.match(line.text)
        if heading_match:
            level = len(heading_match.group(1))
            heading = heading_match.group(2).strip()
            heading_levels = {
                existing_level: value
                for existing_level, value in heading_levels.items()
                if existing_level < level
            }
            heading_levels[level] = heading
            heading_path = _current_heading_path(heading_levels)
            section_start = line.start
            blocks.append(
                _source_block(
                    text,
                    kind="heading",
                    start=line.start,
                    end=line.end,
                    heading_path=heading_path,
                    section_start=section_start,
                )
            )
            index += 1
            continue

        heading_path = _current_heading_path(heading_levels)
        if _is_table_start(lines, index):
            end_index = index + 2
            while end_index < len(lines) and _is_table_row(lines[end_index].text):
                end_index += 1
            blocks.append(
                _source_block(
                    text,
                    kind="table",
                    start=line.start,
                    end=lines[end_index - 1].end,
                    heading_path=heading_path,
                    section_start=section_start,
                )
            )
            index = end_index
            continue

        if _LIST_RE.match(line.text):
            end_index = index + 1
            while end_index < len(lines):
                candidate = lines[end_index].text
                if not candidate.strip():
                    break
                if _HEADING_RE.match(candidate) or _FENCE_RE.match(candidate):
                    break
                if _is_table_start(lines, end_index):
                    break
                if _LIST_RE.match(candidate) or candidate.startswith((" ", "\t")):
                    end_index += 1
                    continue
                break
            blocks.append(
                _source_block(
                    text,
                    kind="list",
                    start=line.start,
                    end=lines[end_index - 1].end,
                    heading_path=heading_path,
                    section_start=section_start,
                )
            )
            index = end_index
            continue

        end_index = index + 1
        while end_index < len(lines):
            candidate = lines[end_index].text
            if not candidate.strip():
                break
            if (
                _HEADING_RE.match(candidate)
                or _FENCE_RE.match(candidate)
                or _LIST_RE.match(candidate)
                or _is_table_start(lines, end_index)
            ):
                break
            end_index += 1
        blocks.append(
            _source_block(
                text,
                kind="prose",
                start=line.start,
                end=lines[end_index - 1].end,
                heading_path=heading_path,
                section_start=section_start,
            )
        )
        index = end_index

    return blocks


def _source_lines(text: str) -> list[_Line]:
    lines = []
    position = 0
    for raw_line in text.splitlines(keepends=True):
        end = position + len(raw_line)
        lines.append(_Line(text=raw_line, start=position, end=end))
        position = end
    if position < len(text):
        lines.append(_Line(text=text[position:], start=position, end=len(text)))
    return lines


def _consume_fence(
    text: str,
    lines: list[_Line],
    start_index: int,
    *,
    heading_path: tuple[str, ...],
    section_start: int,
) -> tuple[_Block, int]:
    opening = _FENCE_RE.match(lines[start_index].text)
    assert opening is not None
    marker = opening.group(1)
    marker_char = marker[0]
    closing_re = re.compile(
        rf"^ {{0,3}}{re.escape(marker_char)}{{{len(marker)},}}[ \t]*(?:\r?\n)?$"
    )

    end_index = start_index + 1
    while end_index < len(lines) and not closing_re.match(lines[end_index].text):
        end_index += 1

    malformed = end_index == len(lines)
    source_end = lines[-1].end if malformed else lines[end_index].end
    content = text[lines[start_index].start : source_end].strip()
    metadata: dict[str, Any] = {
        "_section_start": section_start,
        "fence_marker": marker,
        "fence_info": opening.group(2).strip(),
    }
    if malformed:
        closing = marker
        content = f"{content}\n{closing}"
        metadata.update(
            {
                "malformed_fence": True,
                "synthetic_closing_fence": True,
                "rendered_content_differs": True,
            }
        )
    return (
        _Block(
            kind="code",
            start=lines[start_index].start,
            end=source_end,
            heading_path=heading_path,
            section_heading=heading_path[-1] if heading_path else None,
            content=content,
            metadata=metadata,
        ),
        len(lines) if malformed else end_index + 1,
    )


def _source_block(
    text: str,
    *,
    kind: str,
    start: int,
    end: int,
    heading_path: tuple[str, ...],
    section_start: int,
) -> _Block:
    trimmed = _trimmed_span(text, start, end)
    assert trimmed is not None
    start, end = trimmed
    return _Block(
        kind=kind,
        start=start,
        end=end,
        heading_path=heading_path,
        section_heading=heading_path[-1] if heading_path else None,
        content=text[start:end],
        metadata={"_section_start": section_start},
    )


def _current_heading_path(levels: dict[int, str]) -> tuple[str, ...]:
    return tuple(value for _, value in sorted(levels.items()))


def _is_table_start(lines: list[_Line], index: int) -> bool:
    return (
        index + 1 < len(lines)
        and _is_table_row(lines[index].text)
        and bool(_TABLE_SEPARATOR_RE.match(lines[index + 1].text.strip()))
    )


def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    return "|" in stripped and not _HEADING_RE.match(line) and not _FENCE_RE.match(line)


def _split_block(
    block: _Block,
    *,
    chunk_size: int,
    overlap: int,
    max_oversized_code_chars: int,
) -> list[_Block]:
    if len(block.content) <= chunk_size:
        return [block]
    if block.kind == "code":
        if len(block.content) <= max_oversized_code_chars:
            return [
                _with_metadata(
                    block,
                    oversized_code=True,
                    allowed_oversized_code=True,
                )
            ]
        return _split_oversized_code(block, chunk_size=chunk_size)
    if block.kind == "table":
        return _split_table(block, chunk_size=chunk_size)
    if block.kind == "list":
        return _split_by_lines(block, chunk_size=chunk_size, split_reason="list_items")
    if block.kind == "prose":
        return _split_prose(block, chunk_size=chunk_size, overlap=overlap)
    return _split_by_characters(block, chunk_size=chunk_size, overlap=overlap)


def _split_oversized_code(block: _Block, *, chunk_size: int) -> list[_Block]:
    lines = block.content.splitlines(keepends=True)
    opening = lines[0].rstrip("\r\n")
    marker_match = _FENCE_RE.match(lines[0])
    assert marker_match is not None
    marker = marker_match.group(1)
    has_source_closing = lines[-1].strip().startswith(marker[0] * len(marker))
    body_lines = lines[1:-1] if has_source_closing else lines[1:]
    overhead = len(opening) + len(marker) + 2
    target = max(1, chunk_size - overhead)
    pieces = _pack_text_parts(body_lines, target)
    results = []
    body_offset = block.start + len(lines[0])
    cursor = body_offset
    for piece in pieces:
        source_piece = piece.rstrip("\r\n")
        start = block.content.find(source_piece, cursor - block.start) + block.start
        end = start + len(source_piece)
        results.append(
            _Block(
                kind="code",
                start=start,
                end=end,
                heading_path=block.heading_path,
                section_heading=block.section_heading,
                content=f"{opening}\n{source_piece}\n{marker}",
                metadata={
                    **block.metadata,
                    "_section_start": block.metadata["_section_start"],
                    "oversized_code": True,
                    "synthetic_opening_fence": True,
                    "synthetic_closing_fence": True,
                    "rendered_content_differs": True,
                    "split_reason": "code_lines",
                },
            )
        )
        cursor = end
    return results


def _split_table(block: _Block, *, chunk_size: int) -> list[_Block]:
    lines = block.content.splitlines(keepends=True)
    header = "".join(lines[:2]).rstrip()
    rows = lines[2:]
    target = max(1, chunk_size - len(header) - 1)
    row_groups = _pack_text_parts(rows, target)
    results = []
    cursor = block.start + len("".join(lines[:2]))
    for group in row_groups:
        source_piece = group.rstrip()
        start = block.content.find(source_piece, cursor - block.start) + block.start
        end = start + len(source_piece)
        results.append(
            _Block(
                kind="table",
                start=start,
                end=end,
                heading_path=block.heading_path,
                section_heading=block.section_heading,
                content=f"{header}\n{source_piece}",
                metadata={
                    "_section_start": block.metadata["_section_start"],
                    "synthetic_table_header": True,
                    "rendered_content_differs": True,
                    "split_reason": "table_rows",
                },
            )
        )
        cursor = end
    return results


def _split_by_lines(block: _Block, *, chunk_size: int, split_reason: str) -> list[_Block]:
    pieces = _pack_text_parts(block.content.splitlines(keepends=True), chunk_size)
    return _pieces_to_source_blocks(block, pieces, split_reason=split_reason)


def _split_prose(block: _Block, *, chunk_size: int, overlap: int) -> list[_Block]:
    sentence_parts = _split_with_delimiter(block.content, _SENTENCE_BOUNDARY_RE)
    if len(sentence_parts) > 1:
        pieces = _pack_text_parts(sentence_parts, chunk_size)
        if all(len(piece.strip()) <= chunk_size for piece in pieces):
            return _pieces_to_source_blocks(block, pieces, split_reason="sentences")

    whitespace_parts = re.findall(r"\S+\s*", block.content)
    if any(len(part.strip()) > chunk_size for part in whitespace_parts):
        return _split_by_characters(block, chunk_size=chunk_size, overlap=overlap)
    pieces = _pack_text_parts(whitespace_parts, chunk_size)
    if all(len(piece.strip()) <= chunk_size for piece in pieces):
        return _pieces_to_source_blocks(block, pieces, split_reason="whitespace")
    return _split_by_characters(block, chunk_size=chunk_size, overlap=overlap)


def _split_with_delimiter(text: str, pattern: re.Pattern[str]) -> list[str]:
    parts = []
    start = 0
    for match in pattern.finditer(text):
        parts.append(text[start : match.end()])
        start = match.end()
    if start < len(text):
        parts.append(text[start:])
    return [part for part in parts if part]


def _pack_text_parts(parts: list[str], limit: int) -> list[str]:
    packed: list[str] = []
    current = ""
    for part in parts:
        if len(part) > limit:
            if current:
                packed.append(current)
                current = ""
            packed.extend(part[index : index + limit] for index in range(0, len(part), limit))
        elif current and len(current) + len(part) > limit:
            packed.append(current)
            current = part
        else:
            current += part
    if current:
        packed.append(current)
    return packed


def _pieces_to_source_blocks(
    block: _Block,
    pieces: list[str],
    *,
    split_reason: str,
) -> list[_Block]:
    results = []
    cursor = 0
    for piece in pieces:
        stripped = piece.strip()
        if not stripped:
            continue
        relative_start = block.content.find(stripped, cursor)
        start = block.start + relative_start
        end = start + len(stripped)
        results.append(
            _Block(
                kind=block.kind,
                start=start,
                end=end,
                heading_path=block.heading_path,
                section_heading=block.section_heading,
                content=stripped,
                metadata={**block.metadata, "split_reason": split_reason},
            )
        )
        cursor = relative_start + len(stripped)
    return results


def _split_by_characters(
    block: _Block,
    *,
    chunk_size: int,
    overlap: int,
) -> list[_Block]:
    results = []
    start = 0
    while start < len(block.content):
        end = min(start + chunk_size, len(block.content))
        trimmed = _trimmed_span(block.content, start, end)
        if trimmed is not None:
            relative_start, relative_end = trimmed
            results.append(
                _Block(
                    kind=block.kind,
                    start=block.start + relative_start,
                    end=block.start + relative_end,
                    heading_path=block.heading_path,
                    section_heading=block.section_heading,
                    content=block.content[relative_start:relative_end],
                    metadata={**block.metadata, "split_reason": "character_fallback"},
                )
            )
        if end == len(block.content):
            break
        start += chunk_size - overlap
    return results


def _assemble_chunks(text: str, blocks: list[_Block], *, chunk_size: int) -> list[ChunkDraft]:
    drafts = []
    current: list[_Block] = []
    for block in blocks:
        if not current:
            current = [block]
            continue
        if _blocks_can_combine(text, current, block, chunk_size=chunk_size):
            current.append(block)
        else:
            drafts.append(_draft_from_blocks(text, current))
            current = [block]
    if current:
        drafts.append(_draft_from_blocks(text, current))
    return drafts


def _blocks_can_combine(
    text: str,
    current: list[_Block],
    block: _Block,
    *,
    chunk_size: int,
) -> bool:
    first = current[0]
    if first.heading_path != block.heading_path:
        return False
    if first.metadata.get("_section_start") != block.metadata.get("_section_start"):
        return False
    if any(item.synthetic for item in current) or block.synthetic:
        return False
    current_kinds = {item.kind for item in current if item.kind != "heading"}
    if current_kinds and block.kind not in current_kinds:
        return False
    return len(text[first.start : block.end].strip()) <= chunk_size


def _draft_from_blocks(text: str, blocks: list[_Block]) -> ChunkDraft:
    first, last = blocks[0], blocks[-1]
    metadata = {}
    for block in blocks:
        metadata.update(block.metadata)
    if any(block.synthetic for block in blocks):
        content = "\n\n".join(block.content for block in blocks)
    else:
        trimmed = _trimmed_span(text, first.start, last.end)
        assert trimmed is not None
        start, end = trimmed
        content = text[start:end]
        first = _with_span(first, start=start, end=end)
        last = _with_span(last, start=start, end=end)
    return ChunkDraft(
        content=content,
        heading_path=first.heading_path,
        section_heading=first.section_heading,
        chunk_type=_chunk_type(blocks),
        char_start=first.start,
        char_end=last.end,
        metadata=metadata,
    )


def _chunk_type(blocks: list[_Block]) -> str:
    kinds = {block.kind for block in blocks if block.kind != "heading"}
    if not kinds:
        return "prose"
    if len(kinds) == 1:
        return next(iter(kinds))
    return "mixed"


def _merge_tiny_chunks(
    text: str,
    drafts: list[ChunkDraft],
    *,
    min_chunk_chars: int,
    chunk_size: int,
) -> list[ChunkDraft]:
    if min_chunk_chars == 0:
        return drafts
    counts = defaultdict(int)
    for draft in drafts:
        counts[_draft_section_key(draft)] += 1

    merged: list[ChunkDraft] = []
    index = 0
    while index < len(drafts):
        draft = drafts[index]
        if not _should_merge_tiny(draft, counts=counts, min_chunk_chars=min_chunk_chars):
            merged.append(draft)
            index += 1
            continue
        if merged and _drafts_can_merge(text, merged[-1], draft, chunk_size=chunk_size):
            previous = merged.pop()
            merged.append(_merge_drafts(text, previous, draft))
            index += 1
            continue
        if index + 1 < len(drafts) and _drafts_can_merge(
            text, draft, drafts[index + 1], chunk_size=chunk_size
        ):
            merged.append(_merge_drafts(text, draft, drafts[index + 1]))
            index += 2
            continue
        merged.append(draft)
        index += 1
    return merged


def _should_merge_tiny(
    draft: ChunkDraft,
    *,
    counts: dict[tuple[tuple[str, ...], int | None], int],
    min_chunk_chars: int,
) -> bool:
    if len(draft.content) >= min_chunk_chars:
        return False
    if draft.chunk_type in {"code", "table"}:
        return False
    return counts[_draft_section_key(draft)] > 1


def _drafts_can_merge(
    text: str,
    left: ChunkDraft,
    right: ChunkDraft,
    *,
    chunk_size: int,
) -> bool:
    if left.heading_path != right.heading_path:
        return False
    if left.metadata.get("_section_start") != right.metadata.get("_section_start"):
        return False
    if left.char_start is None or right.char_end is None:
        return False
    if left.metadata.get("rendered_content_differs") or right.metadata.get(
        "rendered_content_differs"
    ):
        return False
    return len(text[left.char_start : right.char_end].strip()) <= chunk_size


def _merge_drafts(text: str, left: ChunkDraft, right: ChunkDraft) -> ChunkDraft:
    assert left.char_start is not None
    assert right.char_end is not None
    trimmed = _trimmed_span(text, left.char_start, right.char_end)
    assert trimmed is not None
    start, end = trimmed
    chunk_type = left.chunk_type if left.chunk_type == right.chunk_type else "mixed"
    return ChunkDraft(
        content=text[start:end],
        heading_path=left.heading_path,
        section_heading=left.section_heading,
        chunk_type=chunk_type,
        char_start=start,
        char_end=end,
        metadata={**left.metadata, **right.metadata, "tiny_chunk_merged": True},
    )


def _finalize_chunks(
    document: SourceDocument,
    drafts: list[ChunkDraft],
    *,
    chunker_version: str,
) -> list[PreparedChunk]:
    occurrences: dict[tuple[str, tuple[str, ...]], int] = defaultdict(int)
    prepared = []
    for index, draft in enumerate(drafts):
        digest = content_hash(draft.content)
        occurrence_key = (digest, draft.heading_path)
        occurrence = occurrences[occurrence_key]
        occurrences[occurrence_key] += 1
        prepared.append(
            PreparedChunk(
                chunk_id=deterministic_chunk_id(
                    source_type=document.source_type,
                    source_path=document.source_path,
                    chunker_version=chunker_version,
                    heading_path=draft.heading_path,
                    chunk_content_hash=digest,
                    same_hash_occurrence=occurrence,
                ),
                content=draft.content,
                chunk_index=index,
                source_type=document.source_type,
                source_path=document.source_path,
                heading_path=draft.heading_path,
                section_heading=draft.section_heading,
                chunk_type=draft.chunk_type,
                char_start=draft.char_start,
                char_end=draft.char_end,
                content_hash=digest,
                chunker_version=chunker_version,
                metadata={
                    **document.metadata,
                    **{
                        key: value
                        for key, value in draft.metadata.items()
                        if not key.startswith("_")
                    },
                },
            )
        )
    return prepared


def _with_metadata(block: _Block, **metadata: Any) -> _Block:
    return _Block(
        kind=block.kind,
        start=block.start,
        end=block.end,
        heading_path=block.heading_path,
        section_heading=block.section_heading,
        content=block.content,
        metadata={**block.metadata, **metadata},
    )


def _with_span(block: _Block, *, start: int, end: int) -> _Block:
    return _Block(
        kind=block.kind,
        start=start,
        end=end,
        heading_path=block.heading_path,
        section_heading=block.section_heading,
        content=block.content,
        metadata=block.metadata,
    )


def _draft_section_key(draft: ChunkDraft) -> tuple[tuple[str, ...], int | None]:
    return draft.heading_path, draft.metadata.get("_section_start")


def _trimmed_span(text: str, start: int, end: int) -> tuple[int, int] | None:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return (start, end) if start < end else None
