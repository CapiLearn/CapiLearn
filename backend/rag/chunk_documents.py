"""Legacy JSON wrapper around the typed RAG chunking contract."""

import json
import re
from pathlib import Path

from backend.rag.chunking import DEFAULT_MIN_CHUNK_CHARS, SourceDocument, prepare_chunks

_HERE = Path(__file__).parent
_DATA_DIR = _HERE.parent / "ingestion"


def load_documents(input_path: str) -> list[dict]:
    path = Path(input_path)
    if not path.is_absolute():
        path = _DATA_DIR / path
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def split_markdown_sections(text: str) -> list[str]:
    """Preserve the original public helper while PR 2 remains deferred."""
    heading_pattern = re.compile(r"(?m)^(#{1,6} .+)")
    parts = heading_pattern.split(text)
    sections = []
    pre_heading = parts[0].strip()
    if pre_heading:
        sections.append(pre_heading)
    for index in range(1, len(parts) - 1, 2):
        heading = parts[index].strip()
        body = parts[index + 1].strip()
        section = (heading + "\n\n" + body).strip() if body else heading
        if section:
            sections.append(section)
    return sections


def split_text_with_overlap(text: str, chunk_size: int, overlap: int) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(text):
            break
        start += chunk_size - overlap
    return chunks


def is_english_source(document: dict) -> bool:
    source_path = document.get("metadata", {}).get("source_path") or ""
    return "/en/" in source_path.replace("\\", "/")


def chunk_document(
    document: dict,
    chunk_size: int,
    overlap: int,
    *,
    source_type: str = "course_repo",
    min_chunk_chars: int = DEFAULT_MIN_CHUNK_CHARS,
) -> list[dict]:
    """Return the historical dictionary shape backed by typed prepared chunks."""
    document_id = str(document["id"])
    metadata = dict(document.get("metadata", {}))
    source_path = metadata.get("source_path") or document_id
    chunks = prepare_chunks(
        SourceDocument(
            content=document.get("content", ""),
            source_type=source_type,
            source_path=source_path,
            document_id=document_id,
            metadata=metadata,
        ),
        chunk_size=chunk_size,
        overlap=overlap,
        min_chunk_chars=min_chunk_chars,
    )
    return [chunk.to_legacy_dict(document_id=document_id) for chunk in chunks]


def chunk_documents(
    input_path: str,
    output_path: str,
    chunk_size: int,
    overlap: int,
) -> None:
    documents = load_documents(input_path)
    print(f"Loaded {len(documents)} source document(s) from '{input_path}'.")

    english_documents = [document for document in documents if is_english_source(document)]
    print(
        f"Selected {len(english_documents)} English document(s) "
        "(filtered by '/en/' in source_path)."
    )

    all_chunks = []
    for document in english_documents:
        all_chunks.extend(chunk_document(document, chunk_size, overlap))

    output_file = Path(output_path)
    if not output_file.is_absolute():
        output_file = _DATA_DIR / output_file
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as file:
        json.dump(all_chunks, file, indent=2, ensure_ascii=False)

    print(f"Created {len(all_chunks)} chunk(s). Saved to '{output_path}'.")


if __name__ == "__main__":
    chunk_documents(
        input_path="data/processed/documents.json",
        output_path="data/processed/chunks.json",
        chunk_size=1000,
        overlap=200,
    )
