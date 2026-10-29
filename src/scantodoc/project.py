"""A project is a folder holding one conversion: the original files, the page
images, the per-page cache, the document model, the chosen style and the
exports. Projects live in ~/ScanToDoc/projects unless told otherwise.

    my-book/
      project.json      name, settings, status
      sources/          copies of the original PDFs/images
      pages/            page-0001.jpg ... (300 DPI)
      cache/            one JSON file per page read
      figures/          pictures cropped from the pages
      document.json     the document model (including your corrections)
      style.json        the current styling options
      exports/          generated .docx, .pdf, .html ...
"""

from __future__ import annotations

import json
import re
import shutil
import threading
from pathlib import Path
from typing import Any, Iterable, Optional

from . import config
from .model import Document, new_id, now_iso

_locks: dict[str, threading.RLock] = {}


def _lock_for(path: Path) -> threading.RLock:
    key = str(path.resolve())
    if key not in _locks:
        _locks[key] = threading.RLock()
    return _locks[key]


def slugify(name: str) -> str:
    s = re.sub(r"[^\w֐-׿-]+", "-", name.strip().lower()).strip("-")
    return s[:60] or "document"


class Project:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.lock = _lock_for(self.root)

    # ---------------------------------------------------------------- paths

    @property
    def meta_path(self) -> Path:
        return self.root / "project.json"

    @property
    def document_path(self) -> Path:
        return self.root / "document.json"

    @property
    def style_path(self) -> Path:
        return self.root / "style.json"

    def dir(self, name: str) -> Path:
        d = self.root / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ---------------------------------------------------------------- create / open

    @classmethod
    def create(cls, name: str, inputs: Iterable[Path], parent: Optional[Path] = None, settings: Optional[dict] = None) -> "Project":
        parent = Path(parent) if parent else config.projects_dir()
        parent.mkdir(parents=True, exist_ok=True)
        base = slugify(name)
        root = parent / base
        n = 2
        while root.exists():
            root = parent / f"{base}-{n}"
            n += 1
        root.mkdir(parents=True)
        proj = cls(root)
        sources = proj.dir("sources")
        copied = []
        for i, f in enumerate(inputs):
            f = Path(f)
            target = sources / f.name
            if target.exists():
                target = sources / f"{i:03d}-{f.name}"
            shutil.copy2(f, target)
            copied.append(target.name)
        proj.save_meta(
            {
                "id": new_id(),
                "name": name,
                "created": now_iso(),
                "updated": now_iso(),
                "sources": copied,
                "settings": settings or {},
                "status": "new",
                "page_count": 0,
            }
        )
        return proj

    @classmethod
    def open(cls, path: Path | str) -> "Project":
        p = Path(path)
        if p.is_file() and p.name in ("project.json", "document.json", "style.json"):
            p = p.parent
        if not (p / "project.json").exists():
            raise FileNotFoundError(f"{p} is not a ScanToDoc project folder.")
        return cls(p)

    # ---------------------------------------------------------------- metadata

    def meta(self) -> dict[str, Any]:
        with self.lock:
            return json.loads(self.meta_path.read_text(encoding="utf-8"))

    def save_meta(self, meta: dict[str, Any]) -> None:
        with self.lock:
            meta["updated"] = now_iso()
            _atomic_write(self.meta_path, json.dumps(meta, ensure_ascii=False, indent=1))

    def update_meta(self, **changes: Any) -> dict[str, Any]:
        with self.lock:
            m = self.meta()
            m.update(changes)
            self.save_meta(m)
            return m

    @property
    def name(self) -> str:
        return self.meta().get("name", self.root.name)

    def source_files(self) -> list[Path]:
        return [self.root / "sources" / s for s in self.meta().get("sources", [])]

    # ---------------------------------------------------------------- document & style

    def load_document(self) -> Optional[Document]:
        with self.lock:
            if not self.document_path.exists():
                return None
            return Document.model_validate_json(self.document_path.read_text(encoding="utf-8"))

    def save_document(self, doc: Document) -> None:
        with self.lock:
            _atomic_write(self.document_path, doc.model_dump_json(indent=1))

    def load_style(self):
        from .style.options import StyleOptions

        with self.lock:
            if not self.style_path.exists():
                return StyleOptions()
            return StyleOptions.model_validate_json(self.style_path.read_text(encoding="utf-8"))

    def save_style(self, style) -> None:
        with self.lock:
            _atomic_write(self.style_path, style.model_dump_json(indent=1))

    def delete(self) -> None:
        shutil.rmtree(self.root)

    def summary(self) -> dict[str, Any]:
        m = self.meta()
        thumb = None
        pages = sorted((self.root / "pages").glob("page-*.jpg")) if (self.root / "pages").exists() else []
        if pages:
            thumb = pages[0].name
        return {
            "id": self.root.name,
            "name": m.get("name"),
            "created": m.get("created"),
            "updated": m.get("updated"),
            "status": m.get("status"),
            "page_count": m.get("page_count", 0),
            "reader": m.get("settings", {}).get("reader"),
            "cost_usd": m.get("cost_usd", 0.0),
            "thumbnail": thumb,
        }


def list_projects(parent: Optional[Path] = None) -> list[Project]:
    parent = Path(parent) if parent else config.projects_dir()
    found = [Project(p) for p in parent.iterdir() if (p / "project.json").exists()] if parent.exists() else []
    return sorted(found, key=lambda pr: pr.meta().get("updated", ""), reverse=True)


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
