from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from backend.rag.schemas import RetrievedChunk

_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class DeduplicationResult:
    chunks: list[RetrievedChunk]
    candidate_count: int
    suppression_reasons: dict[str, int]


def deduplicate_chunks(
    candidates: list[RetrievedChunk],
    *,
    top_k: int,
    overlap_threshold: float = 0.8,
) -> DeduplicationResult:
    retained: list[RetrievedChunk] = []
    reasons: Counter[str] = Counter()

    for candidate in candidates:
        reason = _duplicate_reason(
            candidate,
            retained,
            overlap_threshold=overlap_threshold,
        )
        if reason is not None:
            reasons[reason] += 1
            continue
        retained.append(candidate)

    return DeduplicationResult(
        chunks=retained[:top_k],
        candidate_count=len(candidates),
        suppression_reasons=dict(sorted(reasons.items())),
    )


def _duplicate_reason(
    candidate: RetrievedChunk,
    retained: list[RetrievedChunk],
    *,
    overlap_threshold: float,
) -> str | None:
    metadata = candidate.metadata or {}
    chunk_id = metadata.get("chunk_id") or metadata.get("chunkId")
    digest = metadata.get("content_hash") or metadata.get("contentHash")
    normalized = _normalize_content(candidate.content)

    for existing in retained:
        existing_metadata = existing.metadata or {}
        existing_id = existing_metadata.get("chunk_id") or existing_metadata.get("chunkId")
        if chunk_id is not None and existing_id == chunk_id:
            return "chunk_id"

        existing_digest = existing_metadata.get("content_hash") or existing_metadata.get(
            "contentHash"
        )
        if digest and existing_digest == digest:
            return "content_hash"

        if (not digest or not existing_digest) and normalized == _normalize_content(
            existing.content
        ):
            return "normalized_content"

        if _same_document(metadata, existing_metadata) and _high_offset_overlap(
            metadata,
            existing_metadata,
            threshold=overlap_threshold,
        ):
            return "overlapping_offsets"
    return None


def _normalize_content(content: str) -> str:
    return _WHITESPACE_RE.sub(" ", content).strip()


def _same_document(left: dict, right: dict) -> bool:
    left_id = left.get("document_id") or left.get("documentId")
    right_id = right.get("document_id") or right.get("documentId")
    return left_id is not None and left_id == right_id


def _high_offset_overlap(left: dict, right: dict, *, threshold: float) -> bool:
    left_range = _offset_range(left)
    right_range = _offset_range(right)
    if left_range is None or right_range is None:
        return False
    left_start, left_end = left_range
    right_start, right_end = right_range
    overlap = max(0, min(left_end, right_end) - max(left_start, right_start))
    shorter = min(left_end - left_start, right_end - right_start)
    return shorter > 0 and overlap / shorter >= threshold


def _offset_range(metadata: dict) -> tuple[int, int] | None:
    start = metadata.get("char_start", metadata.get("charStart"))
    end = metadata.get("char_end", metadata.get("charEnd"))
    if not isinstance(start, int) or not isinstance(end, int) or end <= start:
        return None
    return start, end
