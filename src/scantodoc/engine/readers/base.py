"""What every reader receives and returns."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol

from ...model import Block, Region, Usage


@dataclass
class PageInput:
    index: int
    image_path: Path
    width_px: int
    height_px: int
    dpi: int
    text_layer: Optional[dict] = None  # spans from the PDF, when the page has real text
    image_hash: str = ""


@dataclass
class PageResult:
    blocks: list[Block]
    regions: list[Region] = field(default_factory=list)
    quality: Optional[float] = None  # 0-100
    usage: Usage = field(default_factory=Usage)
    reader: str = ""
    model: str = ""
    warnings: list[str] = field(default_factory=list)


class Reader(Protocol):
    name: str

    def cache_key(self) -> str:
        """Identifies everything that changes this reader's output."""

    def read(self, page: PageInput) -> PageResult: ...


class ReaderError(RuntimeError):
    pass
