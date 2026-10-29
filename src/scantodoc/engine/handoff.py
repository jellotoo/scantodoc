"""Let Claude read the pages itself, inside a chat (Claude Code or the Claude
app), with no API key: the skill renders the pages, Claude looks at each page
image and writes one JSON file per page, and `assemble` turns those files into
the same document model every other reader produces.

    prepare  -> pages/page-0001.jpg ... and agent/pages.json (what to read, where to write)
    (Claude) -> agent/page-0001.json ...  (the Claude reader's page format)
    assemble -> validate, crop figures, normalise, document.json

Hand-written JSON may leave out any field that has an obvious default, and a
block or table cell may give "text" instead of "runs".
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Optional

from pydantic import ValidationError

from ..model import Document, Usage
from ..project import Project
from ..text import detect_direction
from .normalize import normalize
from .pipeline import ConvertSettings, crop_figures, prepare_pages
from .readers.claude import PAGE_SCHEMA, SYSTEM_PROMPT, CPage, convert

AGENT_DIR = "agent"

_RUN_DEFAULTS = {
    "bold": False,
    "italic": False,
    "underline": False,
    "strikethrough": False,
    "superscript": False,
    "subscript": False,
    "color": "",
    "uncertain": False,
}
_BLOCK_DEFAULTS = {
    "region": "",
    "list_level": 0,
    "list_marker": "",
    "indent_level": 0,
    "first_line_indent": False,
    "font_size_pt": 0,
    "font_category": "serif",
    "box": [],
    "continues_on_next_page": False,
    "continues_from_previous_page": False,
    "runs": [],
    "table_rows": [],
    "figure_description": "",
}
_REGION_DEFAULTS = {"kind": "other", "font_category": "serif"}


def answer_path(project: Project, page_index: int) -> Path:
    return project.root / AGENT_DIR / f"page-{page_index + 1:04d}.json"


def prepare(
    project: Project,
    settings: Optional[ConvertSettings] = None,
    on_event: Optional[Callable] = None,
    only: Optional[list[int]] = None,
) -> list[dict]:
    """Render the pages and write agent/pages.json, which lists for every page
    the image to look at and the JSON file to write.

    With `only` (0-based page indexes), the project must already have its pages
    (for example from a local conversion): just those pages are handed over,
    and `assemble` keeps the others as they are."""
    settings = settings or ConvertSettings()
    if only is None:
        doc = prepare_pages(project, settings, on_event or (lambda e: None))
    else:
        doc = project.load_document()
        if doc is None or not doc.pages:
            raise ValueError("This project has no pages yet.")
        for i in only:
            stale = answer_path(project, i)
            if stale.exists():
                stale.unlink()
        doc = doc.model_copy(update={"pages": [doc.pages[i] for i in only]})
    folder = project.dir(AGENT_DIR)
    (folder / "schema.json").write_text(json.dumps(PAGE_SCHEMA, indent=1), encoding="utf-8")
    (folder / "reading-rules.md").write_text(SYSTEM_PROMPT + "\n", encoding="utf-8")
    pages = []
    for page in doc.pages:
        image = project.root / page.image
        text_file = None
        tl = image.with_suffix(".text.json")
        if settings.use_text_layer and page.has_text_layer and tl.exists():
            text = json.loads(tl.read_text(encoding="utf-8")).get("text", "")
            if text.strip():
                text_file = folder / f"page-{page.index + 1:04d}.text.txt"
                text_file.write_text(text, encoding="utf-8")
        answer = answer_path(project, page.index)
        pages.append(
            {
                "page": page.index + 1,
                "image": str(image),
                "answer": str(answer),
                "width_in": round(page.width_px / page.dpi, 2),
                "height_in": round(page.height_px / page.dpi, 2),
                "text_layer": str(text_file) if text_file else None,
                "done": answer.exists(),
            }
        )
    (folder / "pages.json").write_text(json.dumps(pages, ensure_ascii=False, indent=1), encoding="utf-8")
    if only is None:
        project.update_meta(status="new", page_count=len(pages), settings={**settings.to_dict(), "reader": "agent"})
    return pages


def fill_defaults(data: Any) -> Any:
    """Complete a hand-written page so it matches the strict schema."""
    if isinstance(data, list):  # just the blocks
        data = {"blocks": data}
    if not isinstance(data, dict):
        raise ValueError("A page must be a JSON object with a \"blocks\" list.")
    data = dict(data)
    data["regions"] = [{**_REGION_DEFAULTS, "label": r.get("id", ""), **r} for r in data.get("regions") or []]
    data["blocks"] = [_block(b) for b in data.get("blocks") or []]
    return data


def _runs(item: dict) -> list[dict]:
    runs = item.get("runs")
    if runs is None and "text" in item:
        runs = [{"text": item["text"]}]
    return [{**_RUN_DEFAULTS, **({"text": r} if isinstance(r, str) else r)} for r in runs or []]


def _block(b: dict) -> dict:
    if not isinstance(b, dict):
        raise ValueError(f"Each block must be a JSON object, not {b!r:.60}.")
    out = {**_BLOCK_DEFAULTS, **{k: v for k, v in b.items() if k != "text"}}
    out["runs"] = _runs(b)
    out.setdefault("heading_level", 1 if b.get("type") == "heading" else 0)
    rows = []
    for row in out["table_rows"]:
        cells = row.get("cells", []) if isinstance(row, dict) else row
        rows.append(
            {
                "cells": [
                    {"colspan": 1, "rowspan": 1, "is_header": False, **{k: v for k, v in c.items() if k != "text"}, "runs": _runs(c)}
                    if isinstance(c, dict)
                    else {"colspan": 1, "rowspan": 1, "is_header": False, "runs": _runs({"text": str(c)})}
                    for c in cells
                ]
            }
        )
    out["table_rows"] = rows
    text = "".join(r["text"] for r in out["runs"]) or " ".join(
        r["text"] for row in rows for c in row["cells"] for r in c["runs"]
    )
    out.setdefault("direction", detect_direction(text))
    out.setdefault("alignment", "right" if out["direction"] == "rtl" else "left")
    return out


def check_page(path: Path) -> CPage:
    """Read and validate one page file; raises ValueError with a readable message."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"not valid JSON ({exc})") from exc
    try:
        return CPage.model_validate(fill_defaults(raw))
    except ValidationError as exc:
        problems = [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:8]]
        raise ValueError("; ".join(problems)) from exc


def assemble(project: Project, allow_missing: bool = False, check_only: bool = False) -> tuple[Optional[Document], list[str]]:
    """Build the document from the page files. Returns (document, problems).
    Nothing is saved when a page is invalid, or missing without allow_missing."""
    doc = project.load_document()
    if doc is None or not doc.pages:
        return None, ["Run `scantodoc prepare` first: this project has no pages yet."]
    problems: list[str] = []
    parsed: dict[int, CPage] = {}
    for page in doc.pages:
        path = answer_path(project, page.index)
        if not path.exists():
            if page.status != "done" or page.reader == "agent":
                problems.append(f"Page {page.index + 1}: {path.name} has not been written yet.")
            continue
        try:
            parsed[page.index] = check_page(path)
        except ValueError as exc:
            problems.append(f"Page {page.index + 1} ({path.name}): {exc}")
    invalid = [p for p in problems if "not been written" not in p]
    if check_only or invalid or (problems and not allow_missing):
        return None, problems
    for page in doc.pages:
        if page.index in parsed:
            blocks, regions = convert(parsed[page.index])
            page.blocks, page.regions = blocks, regions
            page.reader, page.model, page.quality, page.usage = "agent", "", None, Usage()
            page.status, page.error = "done", ""
            crop_figures(project, page)
        elif page.status != "done":
            page.status, page.error = "error", "This page was not read."
    normalize(doc)
    doc.usage = doc.total_usage()
    project.save_document(doc)
    failed = sum(1 for p in doc.pages if p.status == "error")
    project.update_meta(status="partial" if failed else "done", page_count=len(doc.pages))
    return doc, problems
