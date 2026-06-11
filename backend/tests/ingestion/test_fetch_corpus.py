from pathlib import Path

import pytest

from backend.ingestion.fetch_corpus import CORPUS_COMMIT, build_parser, fetch_corpus
from backend.rag.config import RagSettings


def test_fetch_corpus_refuses_nonempty_unexpected_target(tmp_path: Path) -> None:
    target = tmp_path / "corpus"
    target.mkdir()
    (target / "unexpected.txt").write_text("do not replace", encoding="utf-8")

    with pytest.raises(RuntimeError, match="not empty"):
        fetch_corpus(target)


def test_fetch_parser_uses_configured_corpus_path(tmp_path: Path) -> None:
    settings = RagSettings(_env_file=None, corpus_source_path=tmp_path)

    args = build_parser(settings).parse_args([])

    assert args.target_path == tmp_path


def test_fetch_corpus_reuses_expected_checkout(tmp_path: Path) -> None:
    target = tmp_path / "corpus"
    (target / ".git").mkdir(parents=True)

    def runner(command, **kwargs):
        return type("Result", (), {"stdout": f"{CORPUS_COMMIT}\n"})()

    assert fetch_corpus(target, runner=runner) == target.resolve()
