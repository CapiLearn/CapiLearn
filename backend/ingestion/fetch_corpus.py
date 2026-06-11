from __future__ import annotations

import argparse
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

from backend.rag.config import RagSettings

CORPUS_REPOSITORY_URL = "https://github.com/fullstack-hy2020/fullstack-hy2020.github.io.git"
CORPUS_COMMIT = "33aa47f115a666c8c18de7b89e7a4d5bc24034cf"
CORPUS_SPARSE_PATHS = ("src/content/*/en/", "LICENSE", "license.txt")

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


def fetch_corpus(
    target_path: Path,
    *,
    runner: CommandRunner = subprocess.run,
) -> Path:
    target = target_path.resolve()
    if _is_expected_checkout(target, runner=runner):
        print(f"Corpus is already available at {target} ({CORPUS_COMMIT}).")
        return target
    if target.exists() and any(target.iterdir()):
        raise RuntimeError(
            f"Corpus target is not empty and is not the expected checkout: {target}. "
            "Choose an empty RAG_CORPUS_SOURCE_PATH or inspect the directory manually."
        )

    target.mkdir(parents=True, exist_ok=True)
    commands: tuple[Sequence[str], ...] = (
        ("git", "init", str(target)),
        ("git", "-C", str(target), "remote", "add", "origin", CORPUS_REPOSITORY_URL),
        ("git", "-C", str(target), "sparse-checkout", "init", "--no-cone"),
        (
            "git",
            "-C",
            str(target),
            "sparse-checkout",
            "set",
            "--no-cone",
            *CORPUS_SPARSE_PATHS,
        ),
        ("git", "-C", str(target), "fetch", "--depth", "1", "origin", CORPUS_COMMIT),
        ("git", "-C", str(target), "checkout", "--detach", "FETCH_HEAD"),
    )
    try:
        for command in commands:
            runner(command, check=True, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            "Failed to fetch the Full Stack Open corpus. Confirm that git and outbound "
            f"GitHub access are available, then retry for target {target}."
        ) from exc

    if not _is_expected_checkout(target, runner=runner):
        raise RuntimeError(
            f"Corpus fetch completed but {target} is not at expected commit {CORPUS_COMMIT}."
        )
    print(f"Fetched English Full Stack Open sources to {target} ({CORPUS_COMMIT}).")
    return target


def _is_expected_checkout(
    target: Path,
    *,
    runner: CommandRunner,
) -> bool:
    if not (target / ".git").exists():
        return False
    try:
        completed = runner(
            ("git", "-C", str(target), "rev-parse", "HEAD"),
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return False
    return completed.stdout.strip() == CORPUS_COMMIT


def build_parser(settings: RagSettings | None = None) -> argparse.ArgumentParser:
    settings = settings or RagSettings()
    parser = argparse.ArgumentParser(
        description="Fetch the pinned English Full Stack Open corpus for RAG ingestion."
    )
    parser.add_argument(
        "--target-path",
        type=Path,
        default=settings.corpus_source_path,
        help="Destination directory; defaults to RAG_CORPUS_SOURCE_PATH.",
    )
    return parser


def main() -> None:
    settings = RagSettings()
    args = build_parser(settings).parse_args()
    fetch_corpus(args.target_path)


if __name__ == "__main__":
    main()
