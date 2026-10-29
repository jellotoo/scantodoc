from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from scantodoc.engine import tesseract  # noqa: E402

SAMPLES = HERE / "samples"

needs_tesseract = pytest.mark.skipif(
    tesseract.find_tesseract() is None or "heb" not in tesseract.languages(),
    reason="Tesseract with English and Hebrew is not installed",
)


@pytest.fixture(autouse=True)
def scantodoc_home(tmp_path, monkeypatch):
    """Every test gets its own empty ScanToDoc folder and no API key."""
    home = tmp_path / "home"
    monkeypatch.setenv("SCANTODOC_HOME", str(home))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    return home


@pytest.fixture
def sample():
    def get(name: str) -> Path:
        return SAMPLES / f"{name}.pdf"

    return get


def runs_with(doc_or_blocks, predicate):
    from scantodoc.model import Document

    blocks = [b for _, b in doc_or_blocks.iter_blocks()] if isinstance(doc_or_blocks, Document) else doc_or_blocks
    return [r for b in blocks for r in b.runs if predicate(r)]
