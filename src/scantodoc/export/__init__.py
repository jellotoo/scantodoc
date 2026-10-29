"""All exporters behind one function: export(document, style, format, path)."""

from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
from typing import Optional

from ..model import Document
from ..style.options import StyleOptions
from ..style.resolve import resolve

FORMATS = {
    "docx": "Word document (.docx) with real heading styles",
    "pdf": "PDF with real, selectable text",
    "html": "Web page (.html) with the chosen styles",
    "md": "Markdown (.md)",
    "txt": "Plain text (.txt)",
    "json": "ScanToDoc document model (.scantodoc.json) for re-styling later",
}
EXTENSIONS = {"docx": ".docx", "pdf": ".pdf", "html": ".html", "md": ".md", "txt": ".txt", "json": ".scantodoc.json"}
ALIASES = {"markdown": "md", "word": "docx", "text": "txt", "htm": "html", "model": "json"}


def normalize_format(fmt: str) -> str:
    f = fmt.strip().lower().lstrip(".")
    f = ALIASES.get(f, f)
    if f not in FORMATS:
        raise ValueError(f"Unknown format '{fmt}'. Choose from: {', '.join(FORMATS)}")
    return f


def bundle(doc: Document, style: StyleOptions, project_root: Optional[Path]) -> dict:
    """A self-contained JSON bundle: the document model with its pictures inside."""
    data = json.loads(doc.model_dump_json())
    for page in data["pages"]:
        for block in page["blocks"]:
            fig = block.get("figure")
            if fig and fig.get("image") and not fig["image"].startswith("data:") and project_root:
                path = project_root / fig["image"]
                if path.exists():
                    mime = mimetypes.guess_type(path.name)[0] or "image/png"
                    fig["image"] = f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")
    return {"format": "scantodoc", "version": 1, "document": data, "style": style.model_dump()}


def export(doc: Document, style: StyleOptions, fmt: str, path: Path, project_root: Optional[Path] = None) -> Path:
    fmt = normalize_format(fmt)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        path.write_text(json.dumps(bundle(doc, style, project_root), ensure_ascii=False, indent=1), encoding="utf-8")
        return path
    rdoc = resolve(doc, style, project_root)
    if fmt == "docx":
        from .docx import render_docx

        path.write_bytes(render_docx(rdoc))
    elif fmt == "pdf":
        from .pdf import render_pdf

        path.write_bytes(render_pdf(rdoc))
    elif fmt == "html":
        from .html import render_html

        path.write_text(render_html(rdoc), encoding="utf-8")
    elif fmt == "md":
        from .markdown import render_markdown

        figs = path.parent / (path.stem + "_figures")
        md = render_markdown(rdoc, figures_dir=figs, figures_rel=figs.name)
        path.write_text(md, encoding="utf-8")
    elif fmt == "txt":
        from .markdown import render_text

        path.write_text(render_text(rdoc), encoding="utf-8")
    return path


def load_bundle(path: Path) -> tuple[Document, StyleOptions]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("format") == "scantodoc":
        return Document.model_validate(data["document"]), StyleOptions.model_validate(data.get("style") or {})
    return Document.model_validate(data), StyleOptions()
