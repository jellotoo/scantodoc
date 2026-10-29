"""Markdown and plain-text export."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..style.resolve import RBlock, RenderDoc, RRun, figure_bytes

_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]<>#|])")


def _md_escape(t: str) -> str:
    return _MD_SPECIAL.sub(r"\\\1", t)


def _md_run(r: RRun) -> str:
    text = r.text
    if not text.strip():
        return text
    lead = text[: len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()) :]
    core = _md_escape(text.strip())
    if r.superscript:
        core = f"<sup>{core}</sup>"
    elif r.subscript:
        core = f"<sub>{core}</sub>"
    if r.strike:
        core = f"~~{core}~~"
    if r.underline and not r.link:
        core = f"<u>{core}</u>"
    if r.italic:
        core = f"*{core}*"
    if r.bold:
        core = f"**{core}**"
    if r.link:
        core = f"[{core}]({r.link})"
    return lead + core + trail


def _md_runs(runs: list[RRun], heading: bool = False) -> str:
    if heading:
        runs = [RRun(**{**r.__dict__, "bold": False}) for r in runs]
    return "".join(_md_run(r) for r in runs).replace("\n", " ").strip()


def _slug(text: str) -> str:
    s = re.sub(r"[^\w֐-׿\- ]", "", text.lower()).strip()
    return re.sub(r"\s+", "-", s)


def render_markdown(rdoc: RenderDoc, figures_dir: Optional[Path] = None, figures_rel: str = "figures") -> str:
    out: list[str] = []
    if rdoc.title_page:
        out.append(f"# {_md_escape(rdoc.title_text)}")
        if rdoc.subtitle:
            out.append(f"*{_md_escape(rdoc.subtitle)}*")
        if rdoc.author:
            out.append(_md_escape(rdoc.author))
        out.append("---")
    if rdoc.toc and rdoc.headings():
        out.append(f"## {_md_escape(rdoc.toc_title)}")
        for h in rdoc.headings():
            indent = "  " * (min(max(h.level, 1), 4) - 1)
            out.append(f"{indent}- [{_md_escape(h.text.strip())}](#{_slug(h.text)})")
    fig_n = 0
    chunks: list[tuple[str, str]] = [("front", x) for x in out]
    for b in rdoc.blocks:
        if b.dropped:
            continue
        text = _md_runs(b.runs, heading=b.kind == "heading")
        if b.kind == "heading":
            chunks.append(("heading", "#" * min(max(b.level, 1), 4) + " " + text))
        elif b.kind == "list_item":
            m = b.marker.strip()
            indent = "  " * max(b.level, 0)
            if not m or m in "•●▪◦‣∙·-–—*■□":
                chunks.append(("list", f"{indent}- {text}"))
            elif re.fullmatch(r"\d{1,3}[.)]", m):
                chunks.append(("list", f"{indent}{m[:-1]}. {text}"))
            else:
                chunks.append(("list", f"{indent}- {_md_escape(m)} {text}"))
        elif b.kind == "quote":
            chunks.append(("quote", "> " + text))
        elif b.kind == "table":
            chunks.append(("table", _md_table(b)))
        elif b.kind == "figure":
            data = figure_bytes(b.figure_src)
            if data and figures_dir is not None:
                fig_n += 1
                figures_dir.mkdir(parents=True, exist_ok=True)
                name = f"figure-{fig_n}.png"
                (figures_dir / name).write_bytes(data)
                chunks.append(("figure", f"![{_md_escape(b.figure_alt)}]({figures_rel}/{name})"))
        elif b.kind == "region_label":
            chunks.append(("label", f"**{text}**"))
        elif b.kind == "caption":
            chunks.append(("caption", f"*{text.strip('*')}*" if text else ""))
        elif text:
            chunks.append(("para", text))
    parts: list[str] = []
    for i, (kind, text) in enumerate(chunks):
        if i and not (kind == "list" and chunks[i - 1][0] == "list"):
            parts.append("\n")
        parts.append(text.rstrip("\n") + "\n")
    return "".join(parts).strip() + "\n"


def _md_table(b: RBlock) -> str:
    grid: list[list[str]] = []
    for row in b.rows:
        line: list[str] = []
        for c in row:
            line.append(_md_runs(c.runs).replace("|", "\\|") or " ")
            line.extend([" "] * (c.colspan - 1))
        grid.append(line)
    width = max(len(r) for r in grid)
    grid = [r + [" "] * (width - len(r)) for r in grid]
    lines = ["| " + " | ".join(grid[0]) + " |", "|" + "---|" * width]
    lines += ["| " + " | ".join(r) + " |" for r in grid[1:]]
    return "\n".join(lines) + "\n"


def render_text(rdoc: RenderDoc) -> str:
    out: list[str] = []
    if rdoc.title_page:
        out += [rdoc.title_text, rdoc.subtitle, rdoc.author, ""]
    for b in rdoc.blocks:
        if b.dropped or b.kind == "figure":
            if b.kind == "figure" and not b.dropped:
                out.append(f"[Figure{': ' + b.figure_alt if b.figure_alt else ''}]")
                out.append("")
            continue
        if b.kind == "table":
            for row in b.rows:
                cells = []
                for c in row:
                    cells.append("".join(r.text for r in c.runs).strip())
                    cells.extend([""] * (c.colspan - 1))
                out.append("\t".join(cells))
        elif b.kind == "list_item":
            out.append(f"{b.marker or '•'} {b.text.strip()}")
            continue
        else:
            out.append(b.text.strip())
        out.append("")
    return re.sub(r"\n{3,}", "\n\n", "\n".join(x for x in out if x is not None)).strip() + "\n"
