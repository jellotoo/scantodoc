"""The conversion pipeline shared by the command line, the web app and the skill.

    sources -> page images (300 DPI) -> read each page (in parallel, cached)
            -> crop figures -> normalise the whole document -> document.json
"""

from __future__ import annotations

import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from PIL import Image

from ..model import Document, Page, Usage
from ..project import Project
from . import cost as costs
from . import ingest, tesseract
from .cache import PageCache, key_for
from .normalize import normalize
from .readers.base import PageInput, PageResult, ReaderError
from .readers.claude import ClaudeReader
from .readers.local import LocalReader
from .readers.textlayer import TextLayerReader

Event = dict[str, Any]
READERS = ("local", "claude", "hybrid")


@dataclass
class ConvertSettings:
    reader: str = "local"  # local (free, offline) | claude | hybrid (local first, Claude for hard pages)
    model: str = costs.DEFAULT_MODEL
    effort: str = "medium"
    languages: str = "eng+heb"
    dpi: int = ingest.DEFAULT_DPI
    concurrency: int = 4
    hybrid_threshold: float = 85.0  # pages the local reader scores below this go to Claude
    pages: Optional[str] = None  # e.g. "1-10,15"
    use_text_layer: bool = True
    force: bool = False  # re-read pages even if they were read before

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ConvertSettings":
        known = {k: v for k, v in (d or {}).items() if k in cls.__dataclass_fields__}
        return cls(**known)


@dataclass
class Readers:
    local: Optional[LocalReader] = None
    claude: Optional[ClaudeReader] = None
    textlayer: TextLayerReader = field(default_factory=TextLayerReader)


class Cancelled(Exception):
    pass


def make_readers(settings: ConvertSettings, claude_client: Any = None) -> Readers:
    r = Readers()
    if settings.reader in ("local", "hybrid") and tesseract.find_tesseract():
        r.local = LocalReader(settings.languages)
    if settings.reader in ("claude", "hybrid"):
        r.claude = ClaudeReader(settings.model, settings.effort, client=claude_client)
    return r


def prepare_pages(project: Project, settings: ConvertSettings, on_event: Callable[[Event], None]) -> Document:
    """Render the selected pages to images (re-using images already rendered)."""
    files = project.source_files()
    all_pages = ingest.list_pages(files)
    chosen = ingest.parse_page_range(settings.pages, len(all_pages))
    doc = project.load_document() or Document(title=project.name)
    existing = {(p.source, p.source_page): p for p in doc.pages}
    pages: list[Page] = []
    pages_dir = project.dir("pages")
    for n, i in enumerate(chosen):
        src = all_pages[i]
        key = (src.path.name, src.page)
        page = existing.get(key) or Page(index=n, source=src.path.name, source_page=src.page)
        page.index = n
        image_path = pages_dir / f"page-{i + 1:04d}.jpg"
        if not page.image or not (project.root / page.image).exists() or page.dpi != settings.dpi:
            on_event({"type": "render", "page": n, "total": len(chosen)})
            rendered = ingest.render(src, image_path, settings.dpi)
            page.image = f"pages/{image_path.name}"
            page.width_px, page.height_px, page.dpi = rendered.width_px, rendered.height_px, rendered.dpi
            page.has_text_layer = rendered.text_layer is not None
            page.status = "pending"  # a new image must be read (again)
        pages.append(page)
    doc.pages = pages
    project.save_document(doc)
    project.update_meta(page_count=len(pages))
    return doc


def page_input(project: Project, page: Page) -> PageInput:
    image = project.root / page.image
    text_layer = None
    tl = image.with_suffix(".text.json")
    if page.has_text_layer and tl.exists():
        text_layer = json.loads(tl.read_text(encoding="utf-8"))
    digest = hashlib.sha1(image.read_bytes()).hexdigest()
    return PageInput(page.index, image, page.width_px, page.height_px, page.dpi, text_layer, digest)


def read_page(
    project: Project, page: Page, settings: ConvertSettings, readers: Readers, cache: PageCache
) -> PageResult:
    """Read one page with the reader the settings call for (using the cache)."""
    inp = page_input(project, page)

    def cached(reader) -> PageResult:
        key = key_for(inp.image_hash, reader.cache_key())
        if not settings.force:
            hit = cache.get(key)
            if hit is not None:
                return hit
        result = reader.read(inp)
        cache.put(key, result)
        return result

    warnings: list[str] = []
    mode = settings.reader
    if inp.text_layer and settings.use_text_layer and mode in ("local", "hybrid") and not inp.text_layer.get("ocr_layer"):
        return cached(readers.textlayer)

    local_result: Optional[PageResult] = None
    if mode in ("local", "hybrid"):
        if readers.local is None:
            if mode == "local":
                raise ReaderError(_missing_tesseract())
        else:
            local_result = cached(readers.local)
            if mode == "local":
                return local_result

    needs_claude = mode == "claude" or (
        mode == "hybrid"
        and (
            local_result is None
            or (local_result.quality is not None and local_result.quality < settings.hybrid_threshold)
            or bool(local_result.regions)
            or sum(len(b.text) for b in local_result.blocks) < 20
        )
    )
    if needs_claude and readers.claude is not None:
        try:
            result = cached(readers.claude)
            result.warnings = warnings + result.warnings
            return result
        except ReaderError as exc:
            if local_result is None and readers.local is not None and mode == "claude":
                try:
                    local_result = cached(readers.local)
                except Exception:  # noqa: BLE001
                    local_result = None
            if local_result is None:
                raise
            local_result.warnings = [f"Claude could not read this page ({exc}); the free local reading is used instead."]
            return local_result
    if local_result is None:
        raise ReaderError(_missing_tesseract())
    return local_result


def _missing_tesseract() -> str:
    return (
        "Tesseract OCR is not installed, so pages cannot be read for free. Install it "
        "(see README) or choose the Claude reader."
    )


def crop_figures(project: Project, page: Page) -> None:
    figs = [b for b in page.blocks if b.type == "figure" and b.figure is not None and b.bbox]
    if not figs:
        return
    folder = project.dir("figures")
    with Image.open(project.root / page.image) as im:
        im = im.convert("RGB")
        for b in figs:
            if b.figure.image and (project.root / b.figure.image).exists():
                continue
            x0, y0, x1, y1 = b.bbox
            pad = 0.006
            box = (
                int(max(0, x0 - pad) * im.width),
                int(max(0, y0 - pad) * im.height),
                int(min(1, x1 + pad) * im.width),
                int(min(1, y1 + pad) * im.height),
            )
            if box[2] - box[0] < 8 or box[3] - box[1] < 8:
                continue
            name = f"p{page.index + 1:04d}-{b.id}.png"
            im.crop(box).save(folder / name, optimize=True)
            b.figure.image = f"figures/{name}"


def convert(
    project: Project,
    settings: ConvertSettings,
    on_event: Optional[Callable[[Event], None]] = None,
    cancel: Optional[threading.Event] = None,
    claude_client: Any = None,
) -> Document:
    emit = on_event or (lambda e: None)
    project.update_meta(status="converting", settings=settings.to_dict())
    try:
        doc = prepare_pages(project, settings, emit)
        readers = make_readers(settings, claude_client)
        if settings.reader in ("claude", "hybrid") and readers.claude is not None:
            n_claude = len(doc.pages) if settings.reader == "claude" else 0
            w = doc.pages[0].width_px if doc.pages else 2550
            h = doc.pages[0].height_px if doc.pages else 3300
            emit({"type": "estimate", **costs.estimate_pages(n_claude or len(doc.pages), settings.model, w, h)})
        cache = PageCache(project.dir("cache"))
        todo = [p for p in doc.pages if settings.force or p.status != "done"]
        emit({"type": "start", "total": len(doc.pages), "todo": len(todo)})
        save_lock = threading.Lock()
        running = Usage()
        for p in doc.pages:
            running.add(p.usage)

        def work(page: Page) -> tuple[Page, Optional[PageResult], Optional[str]]:
            if cancel is not None and cancel.is_set():
                return page, None, "cancelled"
            emit({"type": "page_start", "page": page.index})
            try:
                return page, read_page(project, page, settings, readers, cache), None
            except Exception as exc:  # noqa: BLE001 - one bad page must not stop the book
                return page, None, str(exc) or exc.__class__.__name__

        for p in todo:
            p.status = "reading"
        with ThreadPoolExecutor(max_workers=max(1, settings.concurrency)) as pool:
            futures = [pool.submit(work, p) for p in todo]
            for fut in as_completed(futures):
                page, result, error = fut.result()
                with save_lock:
                    if error == "cancelled":
                        page.status = "pending"
                        continue
                    if error:
                        page.status = "error"
                        page.error = error
                        emit({"type": "page_error", "page": page.index, "error": error})
                    else:
                        assert result is not None
                        page.blocks = result.blocks
                        page.regions = result.regions
                        page.quality = result.quality
                        page.reader = result.reader or None
                        page.model = result.model
                        page.usage = result.usage
                        page.status = "done"
                        page.error = "; ".join(result.warnings)
                        running.add(result.usage)
                        crop_figures(project, page)
                        emit(
                            {
                                "type": "page_done",
                                "page": page.index,
                                "reader": page.reader,
                                "quality": page.quality,
                                "cost_usd": round(result.usage.cost_usd, 5),
                                "total_cost_usd": round(running.cost_usd, 5),
                                "warning": page.error,
                            }
                        )
                    project.save_document(doc)
        if cancel is not None and cancel.is_set():
            project.save_document(doc)
            project.update_meta(status="cancelled")
            emit({"type": "cancelled"})
            raise Cancelled()
        normalize(doc)
        doc.usage = doc.total_usage()
        project.save_document(doc)
        failed = sum(1 for p in doc.pages if p.status == "error")
        project.update_meta(
            status="done" if not failed else "partial",
            cost_usd=round(doc.usage.cost_usd, 5),
            page_count=len(doc.pages),
        )
        emit({"type": "done", "pages": len(doc.pages), "failed": failed, "cost_usd": round(doc.usage.cost_usd, 5)})
        return doc
    except Cancelled:
        raise
    except Exception as exc:
        project.update_meta(status="error", error=str(exc))
        emit({"type": "error", "error": str(exc)})
        raise


def reread_page(project: Project, page_index: int, settings: ConvertSettings, claude_client: Any = None) -> Document:
    """Read one page again (for example with Claude after a weak local reading)."""
    doc = project.load_document()
    if doc is None:
        raise FileNotFoundError("This project has no document yet.")
    page = doc.pages[page_index]
    readers = make_readers(settings, claude_client)
    result = read_page(project, page, settings, readers, PageCache(project.dir("cache")))
    page.blocks, page.regions, page.quality = result.blocks, result.regions, result.quality
    page.reader, page.model, page.usage, page.status = result.reader or None, result.model, result.usage, "done"
    page.error = "; ".join(result.warnings)
    crop_figures(project, page)
    normalize(doc)
    doc.usage = doc.total_usage()
    project.save_document(doc)
    project.update_meta(cost_usd=round(doc.usage.cost_usd, 5))
    return doc


def convert_files(
    inputs: list[Path],
    name: str,
    settings: ConvertSettings,
    on_event: Optional[Callable[[Event], None]] = None,
    parent: Optional[Path] = None,
    claude_client: Any = None,
) -> tuple[Project, Document]:
    files = ingest.collect_inputs(inputs)
    if not files:
        raise ValueError("No PDF or image files were found in the input.")
    project = Project.create(name, files, parent=parent, settings=settings.to_dict())
    doc = convert(project, settings, on_event, claude_client=claude_client)
    return project, doc
