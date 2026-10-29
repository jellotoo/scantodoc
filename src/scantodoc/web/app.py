"""The ScanToDoc web app: a FastAPI server for the browser interface.

It is a thin layer over the same engine the command line uses. The server
only listens on this computer (127.0.0.1) by default, and the Claude API key
never leaves it: the browser is only ever told *whether* a key is set.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import tempfile
import threading
import zipfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel

from .. import __version__, config
from ..engine import cost as costs
from ..engine import ingest, tesseract
from ..engine.pipeline import Cancelled, ConvertSettings, convert, reread_page
from ..export import EXTENSIONS, FORMATS, export, normalize_format
from ..export.html import preview_html
from ..model import BLOCK_TYPES, Block, Run
from ..project import Project, list_projects
from ..style import fonts as F
from ..style import presets
from ..style.options import StyleOptions, merge
from ..style.resolve import resolve

STATIC_DIR = Path(__file__).resolve().parent / "static"
SAFE_NAME = re.compile(r"^[\w.\-֐-׿ ]+$")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


# ---------------------------------------------------------------- jobs


class Job:
    """One conversion running in a background thread, with its event log."""

    def __init__(self, project: Project, settings: ConvertSettings, claude_client: Any = None):
        self.project = project
        self.settings = settings
        self.events: list[dict] = []
        self.status = "running"
        self.cancel = threading.Event()
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._run, args=(claude_client,), daemon=True)

    def push(self, event: dict) -> None:
        with self.lock:
            self.events.append(event)

    def _run(self, claude_client: Any) -> None:
        try:
            convert(self.project, self.settings, self.push, self.cancel, claude_client=claude_client)
            self.status = "done"
        except Cancelled:
            self.status = "cancelled"
        except Exception as exc:  # noqa: BLE001 - reported to the browser
            if not any(e.get("type") == "error" for e in self.events):
                self.push({"type": "error", "error": str(exc) or exc.__class__.__name__})
            self.status = "error"

    def snapshot(self, start: int) -> list[dict]:
        with self.lock:
            return self.events[start:]


# ---------------------------------------------------------------- request bodies


class ConvertBody(BaseModel):
    reader: str = "local"
    model: str = costs.DEFAULT_MODEL
    effort: str = "medium"
    languages: str = "eng+heb"
    pages: Optional[str] = None
    force: bool = False


class KeyBody(BaseModel):
    key: str


class PresetBody(BaseModel):
    name: str
    description: str = ""
    style: dict = {}


class RunBody(BaseModel):
    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False
    superscript: bool = False
    subscript: bool = False
    color: Optional[str] = None


class BlockPatch(BaseModel):
    type: Optional[str] = None
    level: Optional[int] = None
    align: Optional[str] = None
    direction: Optional[str] = None
    runs: Optional[list[RunBody]] = None
    list_marker: Optional[str] = None


class RenameBody(BaseModel):
    name: str


# ---------------------------------------------------------------- helpers


@lru_cache(maxsize=1)
def _chromium_ok() -> bool:
    from ..browser import available

    return available()


def _system_status() -> dict:
    exe = tesseract.find_tesseract()
    return {
        "tesseract": bool(exe),
        "tesseract_version": tesseract.version() if exe else "",
        "languages": list(tesseract.languages()) if exe else [],
        "chromium": _chromium_ok(),
    }


def _project(pid: str) -> Project:
    if not SAFE_NAME.match(pid) or pid in (".", ".."):
        raise HTTPException(404, "No such project.")
    root = (config.projects_dir() / pid).resolve()
    if root.parent != config.projects_dir().resolve() or not (root / "project.json").exists():
        raise HTTPException(404, "No such project.")
    return Project(root)


def _safe_file(folder: Path, name: str) -> Path:
    if not SAFE_NAME.match(name) or name.startswith("."):
        raise HTTPException(404, "No such file.")
    path = (folder / name).resolve()
    if path.parent != folder.resolve() or not path.is_file():
        raise HTTPException(404, "No such file.")
    return path


def _stem(name: str) -> str:
    keep = "".join(c if c.isalnum() or c in " -_.()" or "֐" <= c <= "׿" else "_" for c in name)
    return keep.strip() or "document"


def _style_from(data: Optional[dict]) -> StyleOptions:
    try:
        return merge(StyleOptions(), data or {})
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"Invalid style: {exc}") from exc


def _thumb(project: Project, image: Path, width: int) -> Path:
    width = max(64, min(width, 2400))
    folder = project.dir("cache") / "thumbs"
    folder.mkdir(exist_ok=True)
    out = folder / f"{image.stem}-w{width}.jpg"
    if not out.exists() or out.stat().st_mtime < image.stat().st_mtime:
        with Image.open(image) as im:
            if im.width > width:
                im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
            im.convert("RGB").save(out, "JPEG", quality=85)
    return out


def _page_count(project: Project) -> tuple[int, int, int]:
    pages = ingest.list_pages(project.source_files())
    w, h = 2550, 3300
    doc = project.load_document()
    if doc and doc.pages and doc.pages[0].width_px:
        w, h = doc.pages[0].width_px, doc.pages[0].height_px
    return len(pages), w, h


def _doc_json(project: Project) -> Optional[dict]:
    doc = project.load_document()
    return json.loads(doc.model_dump_json()) if doc else None


# ---------------------------------------------------------------- app


def _host_name(netloc: str) -> str:
    if netloc.startswith("["):
        return netloc[1 : netloc.find("]")]
    return netloc.rsplit(":", 1)[0] if netloc.count(":") == 1 else netloc


def create_app(claude_client: Any = None, local_only: bool = True) -> FastAPI:
    """The web app. With local_only (the default) it answers only requests made to
    localhost, so other websites cannot reach it through tricks like DNS rebinding."""
    app = FastAPI(title="ScanToDoc", version=__version__, docs_url=None, redoc_url=None)
    jobs: dict[str, Job] = {}
    app.state.jobs = jobs
    app.state.claude_client = claude_client

    @app.middleware("http")
    async def same_origin_only(request: Request, call_next):
        host = request.headers.get("host", "")
        if local_only and _host_name(host) not in LOCAL_HOSTS:
            return JSONResponse({"detail": "ScanToDoc only answers requests to localhost."}, status_code=403)
        origin = request.headers.get("origin")
        if request.method not in ("GET", "HEAD") and origin and urlparse(origin).netloc != host:
            # Another website's page trying to change something here.
            return JSONResponse({"detail": "Requests from other websites are not allowed."}, status_code=403)
        return await call_next(request)

    def job_for(pid: str) -> Optional[Job]:
        return jobs.get(pid)

    # ---------------------------------------------------------------- settings

    @app.get("/api/config")
    def get_config():
        return {
            "version": __version__,
            "has_api_key": config.has_api_key() or app.state.claude_client is not None,
            "home": str(config.home()),
            "models": [{"id": k, "label": p.label, "input": p.input, "output": p.output} for k, p in costs.PRICES.items()],
            "default_model": costs.DEFAULT_MODEL,
            "formats": [{"id": k, "label": v, "ext": EXTENSIONS[k]} for k, v in FORMATS.items()],
            "block_types": list(BLOCK_TYPES),
            **_system_status(),
        }

    @app.post("/api/key")
    def set_key(body: KeyBody):
        key = body.key.strip()
        if not key or any(c.isspace() for c in key) or len(key) < 20:
            raise HTTPException(422, "That does not look like an API key (it should start with sk-ant-).")
        config.save_api_key(key)
        return {"has_api_key": True}

    @app.delete("/api/key")
    def delete_key():
        config.remove_api_key()
        return {"has_api_key": config.has_api_key()}

    @app.get("/api/fonts")
    def get_fonts():
        return {"fonts": F.curated(), "default_latin": F.DEFAULT_LATIN, "default_hebrew": F.DEFAULT_HEBREW}

    # ---------------------------------------------------------------- presets

    @app.get("/api/presets")
    def get_presets():
        return presets.list_presets()

    @app.get("/api/presets/{key}")
    def get_preset(key: str):
        if key not in {p["key"] for p in presets.list_presets()}:
            raise HTTPException(404, "No such preset.")
        return presets.load(key).model_dump()

    @app.post("/api/presets")
    def save_preset(body: PresetBody):
        if not body.name.strip():
            raise HTTPException(422, "Please give the preset a name.")
        builtin = {p["key"] for p in presets.list_presets() if p["builtin"]}
        if presets._key(body.name) in builtin:
            raise HTTPException(409, "A built-in preset already has that name; please choose another.")
        presets.save(_style_from(body.style), body.name.strip(), body.description)
        return presets.list_presets()

    @app.delete("/api/presets/{key}")
    def delete_preset(key: str):
        if not presets.delete(key):
            raise HTTPException(404, "Only saved (not built-in) presets can be deleted.")
        return presets.list_presets()

    # ---------------------------------------------------------------- projects

    @app.get("/api/projects")
    def get_projects():
        out = []
        for p in list_projects(config.projects_dir()):
            s = p.summary()
            if s["status"] == "converting" and not (job_for(s["id"]) and job_for(s["id"]).status == "running"):
                s["status"] = "interrupted"
            out.append(s)
        return out

    @app.post("/api/projects")
    def create_project(files: list[UploadFile] = File(...), name: str = Form("")):
        with tempfile.TemporaryDirectory() as tmp:
            saved = []
            for i, up in enumerate(files):
                fname = Path(up.filename or f"file-{i}").name
                if Path(fname).suffix.lower() not in ingest.PDF_EXT | ingest.IMAGE_EXT:
                    continue
                target = Path(tmp) / fname
                with target.open("wb") as fh:
                    shutil.copyfileobj(up.file, fh)
                saved.append(target)
            if not saved:
                raise HTTPException(422, "Please choose PDF or image files (PDF, PNG, JPG, TIFF...).")
            saved.sort(key=ingest.natural_key)
            try:
                n = len(ingest.list_pages(saved))
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(422, f"Could not open the files: {exc}") from exc
            project = Project.create(name.strip() or saved[0].stem, saved, parent=config.projects_dir())
        project.update_meta(page_count=n)
        return project.summary()

    @app.get("/api/projects/{pid}")
    def get_project(pid: str):
        project = _project(pid)
        job = job_for(pid)
        meta = project.meta()
        status = meta.get("status")
        if status == "converting" and not (job and job.status == "running"):
            status = "interrupted"
        try:
            total, _, _ = _page_count(project)
        except Exception:  # noqa: BLE001
            total = meta.get("page_count", 0)
        return {
            "id": pid,
            "name": meta.get("name"),
            "status": status,
            "settings": meta.get("settings", {}),
            "source_pages": total,
            "sources": meta.get("sources", []),
            "document": _doc_json(project),
            "style": project.load_style().model_dump(),
            "job": {"status": job.status, "events": len(job.events)} if job else None,
        }

    @app.patch("/api/projects/{pid}")
    def rename_project(pid: str, body: RenameBody):
        project = _project(pid)
        if not body.name.strip():
            raise HTTPException(422, "The name cannot be empty.")
        project.update_meta(name=body.name.strip())
        return project.summary()

    @app.delete("/api/projects/{pid}")
    def delete_project(pid: str):
        project = _project(pid)
        job = job_for(pid)
        if job and job.status == "running":
            raise HTTPException(409, "This project is converting; stop it first.")
        project.delete()
        jobs.pop(pid, None)
        return {"deleted": pid}

    # ---------------------------------------------------------------- converting

    @app.post("/api/projects/{pid}/estimate")
    def estimate(pid: str, body: ConvertBody):
        project = _project(pid)
        total, w, h = _page_count(project)
        n = len(ingest.parse_page_range(body.pages, total))
        est = costs.estimate_pages(n if body.reader != "local" else 0, body.model, w, h)
        return {
            "pages": n,
            "reader": body.reader,
            "model": body.model,
            "has_api_key": config.has_api_key() or app.state.claude_client is not None,
            "tesseract": bool(tesseract.find_tesseract()),
            **{k: est[k] for k in ("low", "high", "typical", "per_page")},
            "upper_bound": body.reader == "hybrid",
        }

    @app.post("/api/projects/{pid}/convert")
    def start_convert(pid: str, body: ConvertBody):
        project = _project(pid)
        job = job_for(pid)
        if job and job.status == "running":
            raise HTTPException(409, "This project is already converting.")
        has_key = config.has_api_key() or app.state.claude_client is not None
        if body.reader == "claude" and not has_key:
            raise HTTPException(422, "No Claude API key is set. Add one in Settings, or choose the free local reader.")
        if body.reader in ("local", "hybrid") and not tesseract.find_tesseract():
            raise HTTPException(422, "Tesseract OCR is not installed, so the free local reader cannot run. See the README.")
        if body.model not in costs.PRICES:
            raise HTTPException(422, "Unknown model.")
        try:
            ingest.parse_page_range(body.pages, 10**6)
        except ValueError as exc:
            raise HTTPException(422, "Pages should look like 1-5,8") from exc
        settings = ConvertSettings(
            reader=body.reader if body.reader in ("local", "claude", "hybrid") else "local",
            model=body.model,
            effort=body.effort,
            languages=body.languages,
            pages=body.pages or None,
            force=body.force,
        )
        if settings.reader == "hybrid" and not has_key:
            settings.reader = "local"
        job = Job(project, settings, app.state.claude_client)
        jobs[pid] = job
        job.thread.start()
        return {"status": "running"}

    @app.post("/api/projects/{pid}/cancel")
    def cancel_convert(pid: str):
        _project(pid)
        job = job_for(pid)
        if job and job.status == "running":
            job.cancel.set()
        return {"status": job.status if job else "idle"}

    @app.get("/api/projects/{pid}/events")
    async def events(pid: str, request: Request, since: int = 0):
        _project(pid)

        async def stream():
            pos = max(0, since)
            while True:
                job = job_for(pid)
                if job is None:
                    yield "event: idle\ndata: {}\n\n"
                    return
                for ev in job.snapshot(pos):
                    pos += 1
                    yield f"id: {pos}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
                if job.status != "running" and pos >= len(job.events):
                    yield f"event: end\ndata: {json.dumps({'status': job.status})}\n\n"
                    return
                if await request.is_disconnected():
                    return
                await asyncio.sleep(0.15)

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    @app.post("/api/projects/{pid}/pages/{index}/reread")
    def reread(pid: str, index: int, body: ConvertBody):
        project = _project(pid)
        job = job_for(pid)
        if job and job.status == "running":
            raise HTTPException(409, "Wait for the conversion to finish first.")
        doc = project.load_document()
        if doc is None or not (0 <= index < len(doc.pages)):
            raise HTTPException(404, "No such page.")
        if body.reader == "claude" and not (config.has_api_key() or app.state.claude_client is not None):
            raise HTTPException(422, "No Claude API key is set. Add one in Settings first.")
        settings = ConvertSettings(reader=body.reader, model=body.model, effort=body.effort, languages=body.languages, force=True)
        try:
            doc = reread_page(project, index, settings, claude_client=app.state.claude_client)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, f"Could not read the page: {exc}") from exc
        return {"document": json.loads(doc.model_dump_json())}

    # ---------------------------------------------------------------- images

    @app.get("/api/projects/{pid}/pages/{name}")
    def page_image(pid: str, name: str, w: int = 0):
        project = _project(pid)
        path = _safe_file(project.root / "pages", name)
        if path.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            raise HTTPException(404, "No such file.")
        if w:
            path = _thumb(project, path, w)
        return FileResponse(path, headers={"Cache-Control": "no-cache"})

    @app.get("/api/projects/{pid}/figures/{name}")
    def figure_image(pid: str, name: str):
        project = _project(pid)
        return FileResponse(_safe_file(project.root / "figures", name))

    # ---------------------------------------------------------------- preview and editing

    @app.post("/api/projects/{pid}/preview")
    def preview(pid: str, style: dict, save: bool = True):
        project = _project(pid)
        opts = _style_from(style)
        if save:
            project.save_style(opts)
        doc = project.load_document()
        if doc is None:
            return {"empty": True}
        rdoc = resolve(doc, opts, project.root, preview=True)

        def img_url(b):
            if not b.figure_src:
                return None
            return f"/api/projects/{pid}/figures/{Path(b.figure_src).name}"

        return preview_html(rdoc, img_url)

    @app.patch("/api/projects/{pid}/blocks/{block_id}")
    def patch_block(pid: str, block_id: str, body: BlockPatch):
        project = _project(pid)
        with project.lock:
            doc = project.load_document()
            if doc is None:
                raise HTTPException(404, "No document yet.")
            page, block = doc.find_block(block_id)
            if block is None:
                raise HTTPException(404, "No such block.")
            if body.type is not None:
                if body.type not in BLOCK_TYPES:
                    raise HTTPException(422, "Unknown block type.")
                if body.type in ("table", "figure") and block.type != body.type:
                    raise HTTPException(422, "A block cannot be turned into a table or picture.")
                if block.type in ("table", "figure") and body.type != block.type:
                    raise HTTPException(422, "Tables and pictures keep their type.")
                block.type = body.type  # type: ignore[assignment]
                if body.type == "heading" and body.level is None and not 1 <= block.level <= 4:
                    block.level = 2
                if body.type == "list_item" and body.list_marker is None and not block.list_marker:
                    block.list_marker = "•"
            if body.level is not None:
                block.level = max(0, min(body.level, 4 if block.type == "heading" else 8))
            if body.align is not None:
                if body.align not in ("left", "center", "right", "justify"):
                    raise HTTPException(422, "Unknown alignment.")
                block.align = body.align  # type: ignore[assignment]
            if body.direction is not None:
                if body.direction not in ("ltr", "rtl"):
                    raise HTTPException(422, "Unknown direction.")
                block.direction = body.direction  # type: ignore[assignment]
            if body.list_marker is not None:
                block.list_marker = body.list_marker
            if body.runs is not None:
                if block.type in ("table", "figure"):
                    raise HTTPException(422, "Edit table cells and pictures in the exported file.")
                try:
                    block.runs = [Run(**r.model_dump()) for r in body.runs if r.text]
                except Exception as exc:  # noqa: BLE001
                    raise HTTPException(422, f"Invalid text: {exc}") from exc
            block.user_edited = True
            doc.touch()
            project.save_document(doc)
        return {"block": json.loads(block.model_dump_json()), "page": page.index if page else None}

    @app.delete("/api/projects/{pid}/blocks/{block_id}")
    def delete_block(pid: str, block_id: str):
        project = _project(pid)
        with project.lock:
            doc = project.load_document()
            page, block = doc.find_block(block_id) if doc else (None, None)
            if block is None or page is None:
                raise HTTPException(404, "No such block.")
            page.blocks = [b for b in page.blocks if b.id != block_id]
            doc.touch()
            project.save_document(doc)
        return {"deleted": block_id, "page": page.index}

    @app.post("/api/projects/{pid}/blocks/{block_id}/restore")
    def restore_block(pid: str, block_id: str, body: dict):
        """Undo a delete: put a block back at its old position on its page."""
        project = _project(pid)
        with project.lock:
            doc = project.load_document()
            if doc is None:
                raise HTTPException(404, "No document yet.")
            page_index = int(body.get("page", -1))
            if not 0 <= page_index < len(doc.pages):
                raise HTTPException(404, "No such page.")
            block = Block.model_validate(body.get("block") or {})
            pos = max(0, min(int(body.get("position", 0)), len(doc.pages[page_index].blocks)))
            doc.pages[page_index].blocks.insert(pos, block)
            project.save_document(doc)
        return {"restored": block.id}

    # ---------------------------------------------------------------- exports

    @app.get("/api/projects/{pid}/export/{fmt}")
    def download(pid: str, fmt: str):
        project = _project(pid)
        try:
            fmt = normalize_format(fmt)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        doc = project.load_document()
        if doc is None:
            raise HTTPException(409, "Convert the document first.")
        stem = _stem(project.name)
        out_dir = project.dir("exports")
        target = out_dir / f"{stem}{EXTENSIONS[fmt]}"
        try:
            export(doc, project.load_style(), fmt, target, project.root)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(500, f"Could not create the {fmt.upper()} file: {exc}") from exc
        figs = out_dir / f"{target.stem}_figures"
        if fmt == "md" and figs.is_dir() and any(figs.iterdir()):
            zpath = out_dir / f"{stem}-markdown.zip"
            with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
                z.write(target, target.name)
                for f in sorted(figs.iterdir()):
                    z.write(f, f"{figs.name}/{f.name}")
            return FileResponse(zpath, filename=zpath.name, media_type="application/zip")
        media = {
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "pdf": "application/pdf",
            "html": "text/html; charset=utf-8",
            "md": "text/markdown; charset=utf-8",
            "txt": "text/plain; charset=utf-8",
            "json": "application/json",
        }[fmt]
        return FileResponse(target, filename=target.name, media_type=media)

    # ---------------------------------------------------------------- static files

    app.mount("/fonts", StaticFiles(directory=F.FONTS_DIR), name="fonts")
    if (STATIC_DIR / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found.")
        f = (STATIC_DIR / path).resolve() if path else None
        if f and f.parent == STATIC_DIR.resolve() and f.is_file():
            return FileResponse(f)
        index = STATIC_DIR / "index.html"
        if index.exists():
            return HTMLResponse(index.read_text(encoding="utf-8"), headers={"Cache-Control": "no-cache"})
        return HTMLResponse(
            "<h1>ScanToDoc</h1><p>The web interface has not been built. Run <code>npm run build</code> in scantodoc/frontend.</p>"
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    return app
