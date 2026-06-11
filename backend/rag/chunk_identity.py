import hashlib
import json
from pathlib import PurePosixPath
from uuid import UUID, uuid5

CAPILEARN_CHUNK_NAMESPACE = UUID("7c661d4d-6d9b-4d98-bfd7-e1f4c355329d")


def canonical_source_path(source_path: str) -> str:
    normalized = source_path.replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return str(PurePosixPath(normalized))


def normalize_for_hash(content: str) -> str:
    return content.replace("\r\n", "\n").replace("\r", "\n")


def content_hash(content: str) -> str:
    normalized = normalize_for_hash(content)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def deterministic_chunk_id(
    *,
    source_type: str,
    source_path: str,
    chunker_version: str,
    heading_path: tuple[str, ...],
    chunk_content_hash: str,
    same_hash_occurrence: int,
) -> UUID:
    identity = json.dumps(
        {
            "source_type": source_type,
            "source_path": canonical_source_path(source_path),
            "chunker_version": chunker_version,
            "heading_path": heading_path,
            "content_hash": chunk_content_hash,
            "same_hash_occurrence": same_hash_occurrence,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return uuid5(CAPILEARN_CHUNK_NAMESPACE, identity)
