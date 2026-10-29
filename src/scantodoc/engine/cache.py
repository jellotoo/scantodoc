"""Per-page cache: once a page has been read, its result is kept on disk.

The key combines the page image's fingerprint with everything that changes
the reader's output (reader, model, prompt version, OCR languages), so a
crash, a re-style or a re-export never reads (or pays for) a page twice.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

from ..model import Block, Region, Usage
from .readers.base import PageResult


def key_for(image_hash: str, reader_key: str) -> str:
    return hashlib.sha1(f"{image_hash}|{reader_key}".encode()).hexdigest()[:24]


class PageCache:
    def __init__(self, folder: Path):
        self.folder = folder
        folder.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.folder / f"{key}.json"

    def get(self, key: str) -> Optional[PageResult]:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return PageResult(
                blocks=[Block.model_validate(b) for b in data["blocks"]],
                regions=[Region.model_validate(r) for r in data.get("regions", [])],
                quality=data.get("quality"),
                usage=Usage(),  # a cached read costs nothing now
                reader=data.get("reader", ""),
                model=data.get("model", ""),
                warnings=data.get("warnings", []),
            )
        except (OSError, ValueError, KeyError):
            return None

    def put(self, key: str, result: PageResult) -> None:
        data = {
            "blocks": [b.model_dump(mode="json") for b in result.blocks],
            "regions": [r.model_dump(mode="json") for r in result.regions],
            "quality": result.quality,
            "reader": result.reader,
            "model": result.model,
            "warnings": result.warnings,
            "usage": result.usage.model_dump(mode="json"),
        }
        tmp = self._path(key).with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._path(key))
