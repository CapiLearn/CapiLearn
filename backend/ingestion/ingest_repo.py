from pathlib import Path
import json

ALLOWED_EXTENSIONS = {".md", ".txt", ".py", ".ipynb"}

SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".next",
    "dist",
    "build",
}


def should_skip(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def find_course_files(repo_root: Path) -> list[Path]:
    files = []

    for path in repo_root.rglob("*"):
        if should_skip(path):
            continue

        if path.is_file() and path.suffix.lower() in ALLOWED_EXTENSIONS:
            files.append(path)

    return files


def load_file(path: Path) -> str:
    if path.suffix.lower() == ".ipynb":
        return load_notebook(path)

    return path.read_text(encoding="utf-8", errors="ignore")


def load_notebook(path: Path) -> str:
    notebook = json.loads(path.read_text(encoding="utf-8", errors="ignore"))

    cells_text = []
    for cell in notebook.get("cells", []):
        source = cell.get("source", [])
        if isinstance(source, list):
            source = "".join(source)

        cell_type = cell.get("cell_type", "unknown")
        cells_text.append(f"\n[{cell_type} cell]\n{source}")

    return "\n".join(cells_text)


def extract_metadata(path: Path, repo_root: Path) -> dict:
    relative_path = path.relative_to(repo_root)
    parts = relative_path.parts

    week = next((part for part in parts if "week" in part.lower()), None)
    day = next((part for part in parts if "day" in part.lower()), None)

    return {
        "source_path": str(relative_path),
        "file_name": path.name,
        "file_type": path.suffix.lower(),
        "week": week,
        "day": day,
    }


def make_document(path: Path, repo_root: Path) -> dict:
    content = load_file(path)
    metadata = extract_metadata(path, repo_root)

    return {
        "id": str(path.relative_to(repo_root)),
        "content": content.strip(),
        "metadata": metadata,
    }


def ingest_repo(repo_path: str, output_path: str = "data/processed/documents.json") -> None:
    repo_root = Path(repo_path).resolve()
    output_file = Path(output_path)

    if not repo_root.exists():
        raise FileNotFoundError(f"Repo path does not exist: {repo_root}")

    files = find_course_files(repo_root)

    documents = []
    for file_path in files:
        document = make_document(file_path, repo_root)

        if document["content"]:
            documents.append(document)

    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open("w", encoding="utf-8") as f:
        json.dump(documents, f, indent=2, ensure_ascii=False)

    print(f"Ingested {len(documents)} documents.")
    print(f"Saved output to: {output_file}")


if __name__ == "__main__":
    ingest_repo(
        repo_path="data/raw/fullstack-hy2020.github.io",
        output_path="data/processed/documents.json",
    )