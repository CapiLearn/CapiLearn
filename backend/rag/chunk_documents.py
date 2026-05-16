"""
chunk_documents.py

Loads documents from data/processed/documents.json,
splits them into RAG-friendly chunks using Markdown-aware splitting,
and saves the result to data/processed/chunks.json.
"""

import json
import re
import uuid
from pathlib import Path

# Directory that contains this script (backend/rag/)
_HERE = Path(__file__).parent

# The data folder sits one level up, inside the ingestion package
_DATA_DIR = _HERE.parent / "ingestion"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_documents(input_path: str) -> list[dict]:
    """Load documents from a JSON file and return them as a list of dicts."""
    path = Path(input_path)
    # If the caller passed a relative path, resolve it from the data directory
    if not path.is_absolute():
        path = _DATA_DIR / path
    with path.open(encoding="utf-8") as f:
        documents = json.load(f)
    return documents


# ---------------------------------------------------------------------------
# Text splitting helpers
# ---------------------------------------------------------------------------


def split_markdown_sections(text: str) -> list[str]:
    """
    Split text on Markdown headings (lines starting with one or more '#').

    Each heading and the content that follows it becomes one section.
    If there is content before the first heading it is kept as its own section.
    """
    # Pattern matches a heading at the start of a line
    heading_pattern = re.compile(r"(?m)^(#{1,6} .+)")
    parts = heading_pattern.split(text)

    sections: list[str] = []

    # parts alternates between: [pre-heading text, heading, body, heading, body, ...]
    # Index 0 is any text before the first heading
    pre_heading = parts[0].strip()
    if pre_heading:
        sections.append(pre_heading)

    # Walk the remaining pairs (heading, body)
    i = 1
    while i < len(parts) - 1:
        heading = parts[i].strip()
        body = parts[i + 1].strip()
        section = (heading + "\n\n" + body).strip() if body else heading
        if section:
            sections.append(section)
        i += 2

    return sections


def split_text_with_overlap(text: str, chunk_size: int, overlap: int) -> list[str]:
    """
    Split *text* into chunks of at most *chunk_size* characters with
    *overlap* characters of context carried over from the previous chunk.

    Empty chunks are discarded.
    """
    chunks: list[str] = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == text_len:
            break
        # Move forward by chunk_size minus the overlap
        start += chunk_size - overlap

    return chunks


# ---------------------------------------------------------------------------
# Language filter
# ---------------------------------------------------------------------------


def is_english_source(document: dict) -> bool:
    """
    Return True only when the document's source_path clearly indicates
    English content.

    For Full Stack Open the English files live under a path segment named
    'en', e.g.  src/content/9/en/part9d.md.  Both forward- and
    back-slash variants are checked so the filter works on every OS.
    """
    source_path: str = document.get("metadata", {}).get("source_path") or ""
    # Normalise to forward slashes for a single comparison
    normalised = source_path.replace("\\", "/")
    return "/en/" in normalised


# ---------------------------------------------------------------------------
# Document chunking
# ---------------------------------------------------------------------------


def chunk_document(document: dict, chunk_size: int, overlap: int) -> list[dict]:
    """
    Split a single document into chunks.

    Strategy:
    1. Split the document content on Markdown headings to get sections.
    2. For each section, if it fits within chunk_size emit it as-is;
       otherwise split it further by character count with overlap.
    3. Attach the original document metadata plus chunk-level fields to
       every chunk.
    """
    doc_id = document["id"]
    content = document.get("content", "")
    metadata = document.get("metadata", {})

    # Step 1 – Markdown-aware split into sections
    sections = split_markdown_sections(content)

    # If the splitter returned nothing (e.g. empty content) bail out early
    if not sections:
        return []

    # Step 2 – further split any section that exceeds chunk_size
    raw_chunks: list[str] = []
    for section in sections:
        if len(section) <= chunk_size:
            raw_chunks.append(section)
        else:
            raw_chunks.extend(split_text_with_overlap(section, chunk_size, overlap))

    # Step 3 – build structured chunk dicts
    chunks: list[dict] = []
    for index, chunk_text in enumerate(raw_chunks):
        chunk_text = chunk_text.strip()
        if not chunk_text:
            continue
        chunks.append(
            {
                "chunk_id": str(uuid.uuid4()),
                "document_id": doc_id,
                "chunk_index": index,
                "content": chunk_text,
                "metadata": metadata,
            }
        )

    return chunks


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def chunk_documents(
    input_path: str,
    output_path: str,
    chunk_size: int,
    overlap: int,
) -> None:
    """
    Load documents from *input_path*, chunk them, and write the result to
    *output_path*.

    Prints a summary of how many source documents were loaded and how many
    chunks were produced.
    """
    documents = load_documents(input_path)
    print(f"Loaded {len(documents)} source document(s) from '{input_path}'.")

    english_documents = [doc for doc in documents if is_english_source(doc)]
    print(
        f"Selected {len(english_documents)} English document(s) "
        "(filtered by '/en/' in source_path)."
    )

    all_chunks: list[dict] = []
    for document in english_documents:
        all_chunks.extend(chunk_document(document, chunk_size, overlap))

    # Ensure the output directory exists
    output_file = Path(output_path)
    if not output_file.is_absolute():
        output_file = _DATA_DIR / output_file
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open("w", encoding="utf-8") as f:
        json.dump(all_chunks, f, indent=2, ensure_ascii=False)

    print(f"Created {len(all_chunks)} chunk(s). Saved to '{output_path}'.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    chunk_documents(
        input_path="data/processed/documents.json",
        output_path="data/processed/chunks.json",
        chunk_size=1000,
        overlap=200,
    )
