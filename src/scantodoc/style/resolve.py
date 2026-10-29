"""Apply styling options to a document: the step every exporter shares.

1. Build the reading *flow*: pages in order, regions arranged as chosen,
   running heads and printed page numbers dropped (unless kept), and
   paragraphs that were split by a page break joined again.
2. Resolve the final style of every block and run: fonts (Latin and Hebrew),
   size, colour, emphasis, alignment, spacing.

The result (RenderDoc) holds plain values, so the Word, HTML, PDF, Markdown
and text exporters all show exactly the same thing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..model import Block, Document, Run, element_key
from ..text import dehyphenate_join, ends_sentence, split_by_direction, strip_marks
from . import fonts as F
from .options import StyleOptions

DEFAULT_SIZE = {
    "body": 12.0, "h1": 24.0, "h2": 18.0, "h3": 14.0, "h4": 12.0, "list": 12.0, "table": 11.0,
    "caption": 10.0, "footnote": 9.0, "quote": 12.0, "header": 9.0, "footer": 9.0, "region": 11.0,
}
SPACE = {  # (before, after) in points when not set by the user
    "body": (0, 6), "h1": (18, 10), "h2": (14, 8), "h3": (12, 6), "h4": (10, 4), "list": (0, 3),
    "table": (6, 8), "caption": (4, 10), "footnote": (2, 2), "quote": (6, 8), "header": (0, 6),
    "footer": (6, 0), "region": (12, 4), "figure": (8, 4),
}
PAGE_SIZES = {"letter": (8.5, 11.0), "a4": (8.27, 11.69), "legal": (8.5, 14.0), "a5": (5.83, 8.27)}
URL = re.compile(r"(https?://[^\s<>\"]+[^\s<>\".,;:!?)\]]|www\.[^\s<>\"]+[^\s<>\".,;:!?)\]]|[\w.+-]+@[\w-]+\.[\w.-]+\w)")
BODY_TYPES = ("paragraph", "list_item", "quote")


@dataclass
class RRun:
    text: str
    rtl: bool = False
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False
    superscript: bool = False
    subscript: bool = False
    color: Optional[str] = None
    link: Optional[str] = None
    uncertain: bool = False
    confidence: Optional[float] = None


@dataclass
class RStyle:
    element: str
    font_latin: str
    font_hebrew: str
    category: str
    size: float
    color: Optional[str]
    bold: bool  # the element's base weight (headings)
    italic: bool
    align: str  # left | center | right | justify (physical)
    direction: str
    indent: float  # start-side indent, points
    end_indent: float
    first_line: float
    space_before: float
    space_after: float
    line_spacing: Optional[float]

    def stack(self, hebrew: bool) -> list[str]:
        return F.font_stack(self.font_hebrew if hebrew else self.font_latin, self.category, hebrew)


@dataclass
class RCell:
    runs: list[RRun]
    colspan: int = 1
    rowspan: int = 1
    header: bool = False


@dataclass
class RBlock:
    id: str
    kind: str  # heading paragraph list_item table caption footnote quote figure header footer page_number region_label
    style: RStyle
    runs: list[RRun] = field(default_factory=list)
    level: int = 0
    marker: str = ""
    rows: list[list[RCell]] = field(default_factory=list)
    figure_src: Optional[str] = None  # absolute file path or data: URI
    figure_width: float = 0.5  # fraction of the text width
    figure_alt: str = ""
    page: int = 0
    source_ids: list[str] = field(default_factory=list)
    dropped: bool = False  # only shown in the preview (e.g. a running head that exports leave out)
    continued: bool = False

    @property
    def text(self) -> str:
        if self.rows:
            return "\n".join("\t".join("".join(r.text for r in c.runs) for c in row) for row in self.rows)
        return "".join(r.text for r in self.runs)


@dataclass
class RenderDoc:
    title: str
    blocks: list[RBlock]
    style: StyleOptions
    direction: str
    page_w: float  # inches
    page_h: float
    margins: tuple[float, float, float, float]  # top, right, bottom, left (inches)
    columns: int
    background: Optional[str]
    accent: Optional[str]
    accent_style: str
    link_color: str
    base: RStyle  # body style, used for document defaults
    element_styles: dict[str, RStyle]
    toc: bool
    toc_title: str
    page_numbers: bool
    page_number_align: str
    title_page: bool
    title_text: str
    subtitle: str
    author: str
    project_root: Optional[Path] = None

    @property
    def text_width(self) -> float:
        return self.page_w - self.margins[1] - self.margins[3]

    def headings(self) -> list[RBlock]:
        return [b for b in self.blocks if b.kind == "heading" and not b.dropped]


# ---------------------------------------------------------------- flow


def figure_bytes(src: Optional[str]) -> Optional[bytes]:
    if not src:
        return None
    if src.startswith("data:"):
        import base64

        return base64.b64decode(src.split(",", 1)[1])
    try:
        return Path(src).read_bytes()
    except OSError:
        return None


def _merge_into(a: Block, b: Block) -> Block:
    m = a.model_copy(deep=True)
    if not m.runs or not b.runs:
        m.runs = m.runs + [r.model_copy() for r in b.runs]
        return m
    last = m.runs[-1]
    first = b.runs[0].model_copy()
    joined = dehyphenate_join(last.text, first.text)
    if joined == last.text.rstrip()[:-1] + first.text.lstrip():  # hyphen removed
        last.text = last.text.rstrip()[:-1]
        first.text = first.text.lstrip()
    elif joined == last.text.rstrip() + first.text.lstrip():
        last.text = last.text.rstrip()
        first.text = first.text.lstrip()
    else:
        last.text = last.text.rstrip()
        first.text = " " + first.text.lstrip()
    m.runs.append(first)
    m.runs.extend(r.model_copy() for r in b.runs[1:])
    return m


def _label(page: Optional[int], rid: str, text: str, blocks: list[Block]) -> Block:
    rtl = sum(len(b.text) for b in blocks if b.direction == "rtl") > sum(len(b.text) for b in blocks if b.direction != "rtl")
    return Block(
        id=f"label-{rid}" if page is None else f"label-{page}-{rid}",
        type="paragraph",
        runs=[Run(text=text)],
        region="__label__",
        direction="rtl" if rtl else "ltr",
        align="right" if rtl else "left",
    )


def build_flow(doc: Document, opts: StyleOptions, preview: bool = False) -> list[tuple[int, Block, bool]]:
    """Blocks in reading order as (page index, block, dropped)."""
    ex = opts.extras
    out: list[tuple[int, Block, bool]] = []
    grouped_tail: dict[str, list[tuple[int, Block, bool]]] = {}
    labels: dict[str, str] = {}
    for page in doc.pages:
        if page.status != "done":
            continue
        regions = sorted(page.regions, key=lambda r: r.order)
        for r in regions:
            labels.setdefault(r.id, r.label or r.id)
        main_ids = {""} | {r.id for r in regions if r.kind == "main"}
        if not regions:
            order = [""]
        else:
            order = [r.id for r in regions]
            if "" not in order:
                order = [""] + order
        for rid in order:
            blocks = [b for b in page.blocks if (b.region or "") == rid or (rid == "" and (b.region or "") not in {r.id for r in regions})]
            if rid in main_ids or rid == "":
                target = out
            elif ex.regions == "main_only":
                continue
            elif ex.regions == "grouped":
                target = grouped_tail.setdefault(rid, [])
            else:
                target = out
                if blocks:
                    out.append((page.index, _label(page.index, rid, labels.get(rid, rid), blocks), False))
            for b in blocks:
                dropped = False
                if b.type in ("header", "footer") and not ex.keep_headers_footers:
                    dropped = True
                if b.type == "page_number" and not ex.keep_page_numbers:
                    dropped = True
                if b.type == "figure" and not ex.include_figures:
                    dropped = True
                if dropped and not preview:
                    continue
                target.append((page.index, b, dropped))
    for rid, items in grouped_tail.items():
        out.append((items[0][0], _label(None, rid, labels.get(rid, rid), [b for _, b, _ in items]), False))
        out.extend(items)
    if preview or not ex.merge_across_pages:
        return out
    merged: list[tuple[int, Block, bool]] = []
    pending: Optional[int] = None  # index in merged of a block waiting for its continuation
    for page_idx, b, dropped in out:
        if b.continued and pending is not None and merged[pending][1].type == b.type:
            p_page, p_block, p_dropped = merged[pending]
            merged[pending] = (p_page, _merge_into(p_block, b), p_dropped)
            pending = pending if b.continues else None
            continue
        merged.append((page_idx, b, dropped))
        if b.type in BODY_TYPES:
            pending = len(merged) - 1 if b.continues else None
        elif b.type not in ("footnote", "header", "footer", "page_number", "figure", "caption"):
            pending = None
    return merged


# ---------------------------------------------------------------- styles


def _page_size(doc: Document, opts: StyleOptions) -> tuple[float, float]:
    p = opts.page
    if p.size == "custom":
        w, h = p.width_in, p.height_in
    elif p.size in PAGE_SIZES:
        w, h = PAGE_SIZES[p.size]
    else:
        first = next((pg for pg in doc.pages if pg.width_px), None)
        if first:
            w, h = first.width_px / first.dpi, first.height_px / first.dpi
            for std in PAGE_SIZES.values():  # snap scans that are almost a standard size
                if abs(w - std[0]) < 0.25 and abs(h - std[1]) < 0.3:
                    w, h = std
                    break
        else:
            w, h = PAGE_SIZES["letter"]
    if p.orientation == "landscape" and h > w or p.orientation == "portrait" and w > h and p.size != "keep":
        w, h = h, w
    return round(w, 3), round(h, 3)


def _detected(doc: Document, element: str, block: Optional[Block]):
    d = doc.detected.get(element)
    size = (d.font_size if d and d.font_size else None) or (block.font_size if block and block.font_size else None)
    category = (d.font_category if d else None) or (block.font_category if block else "serif")
    return d, size, category


def element_style(doc: Document, opts: StyleOptions, element: str, block: Optional[Block] = None) -> RStyle:
    d, size, category = _detected(doc, element, block)
    if block is not None and block.font_category in ("rashi", "monospace"):
        category = block.font_category  # a Rashi-script commentary keeps its script
    fonts = opts.font_for(element)
    latin = fonts.latin or F.DEFAULT_LATIN.get(category, "Times New Roman")
    hebrew = fonts.hebrew or F.DEFAULT_HEBREW.get(category, "David")
    if category == "rashi":
        hebrew = rashi_font(opts)
    # size
    s = opts.sizes
    base_size = size or DEFAULT_SIZE.get(element, 12.0)
    if s.mode == "exact":
        base_size = s.exact.get(element) or (s.exact.get("body") if element in ("list", "quote") else None) or base_size
    elif s.mode == "scale":
        base_size = base_size * s.scale / 100.0
    base_size = round(base_size * 2) / 2
    # colour of the element as a whole
    c = opts.colors
    color = None
    if c.mode == "custom":
        color = c.custom.get(element) or (c.custom.get("headings") if element.startswith("h") and len(element) == 2 else None)
        if color is None and element in ("list", "quote", "table", "caption", "footnote"):
            color = c.custom.get("body")
    elif c.mode == "keep" and d is not None:
        color = d.color
    bold = bool(d.bold) if d is not None else element.startswith("h") and len(element) == 2
    italic = bool(d.italic) if d is not None else False
    if element.startswith("h") and len(element) == 2 and d is None:
        bold = True
    before, after = SPACE.get(element, (0, 6))
    sp = opts.spacing
    if element in ("body", "list", "quote"):
        if sp.space_before is not None:
            before = sp.space_before
        if sp.space_after is not None:
            after = sp.space_after if element == "body" else min(sp.space_after, after if element == "list" else sp.space_after)
    line = sp.line_spacing
    if element.startswith("h") and len(element) == 2:
        line = None if line is None else min(line, 1.15)
    return RStyle(
        element=element,
        font_latin=latin,
        font_hebrew=hebrew,
        category=category,
        size=base_size,
        color=color,
        bold=bold,
        italic=italic,
        align="left",
        direction="ltr",
        indent=0.0,
        end_indent=0.0,
        first_line=0.0,
        space_before=float(before),
        space_after=float(after),
        line_spacing=line,
    )


def rashi_font(opts: StyleOptions) -> str:
    own = opts.fonts.elements.get("rashi")
    return (own.hebrew if own and own.hebrew else None) or "Noto Rashi Hebrew"


def _align(block: Block, element: str, opts: StyleOptions) -> str:
    mode = opts.alignment.mode
    is_heading = element.startswith("h") and len(element) == 2
    if mode == "keep" or (is_heading and not opts.alignment.headings) or element in ("caption", "header", "footer", "figure"):
        align = block.align
    elif mode == "start":
        align = "right" if block.direction == "rtl" else "left"
    else:
        align = mode
    return align


def _runs(block_runs: list[Run], block: Block, style: RStyle, opts: StyleOptions, base_dir: str) -> list[RRun]:
    em = opts.emphasis
    c = opts.colors
    out: list[RRun] = []
    for r in block_runs:
        text = r.text
        if opts.extras.strip_nikud or opts.extras.strip_teamim:
            text = strip_marks(text, nikud=opts.extras.strip_nikud, teamim=opts.extras.strip_teamim)
        if not text:
            continue
        color = r.color
        if c.mode == "black":
            color = None
        elif c.mode == "custom" and style.color:
            color = style.color
        elif c.mode == "keep" and color is None:
            color = None
        bold = r.bold and em.bold
        italic = r.italic and em.italic
        is_heading = style.element.startswith("h") and len(style.element) == 2
        if is_heading:
            # Headings carry their weight in the heading style itself.
            bold = style.bold or bold if em.bold else style.bold
        for seg, d in split_by_direction(text, base_dir):
            pieces = _linkify(seg) if opts.extras.link_urls else [(seg, None)]
            for piece, link in pieces:
                out.append(
                    RRun(
                        text=piece,
                        rtl=d == "rtl",
                        bold=bold,
                        italic=italic,
                        underline=(r.underline and em.underline) or bool(link),
                        strike=r.strike and em.strike,
                        superscript=r.superscript,
                        subscript=r.subscript,
                        color=(c.link or "#1D4ED8") if link else color,
                        link=link,
                        uncertain=r.uncertain,
                        confidence=r.confidence,
                    )
                )
    return out


def _linkify(text: str) -> list[tuple[str, Optional[str]]]:
    out: list[tuple[str, Optional[str]]] = []
    pos = 0
    for m in URL.finditer(text):
        if m.start() > pos:
            out.append((text[pos : m.start()], None))
        target = m.group(0)
        href = target if target.startswith("http") else (f"mailto:{target}" if "@" in target and "/" not in target else f"https://{target}")
        out.append((target, href))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], None))
    return out or [(text, None)]


def _bold_line_heading(b: Block, opts: StyleOptions) -> bool:
    if not opts.emphasis.bold_lines_to_headings or b.type != "paragraph":
        return False
    t = b.text.strip()
    runs = [r for r in b.runs if r.text.strip()]
    return bool(runs) and all(r.bold for r in runs) and 0 < len(t) <= 100 and (not ends_sentence(t) or t.endswith(":"))


def resolve(doc: Document, opts: StyleOptions, project_root: Optional[Path] = None, preview: bool = False) -> RenderDoc:
    flow = build_flow(doc, opts, preview=preview)
    element_styles: dict[str, RStyle] = {}

    def style_for(element: str, block: Optional[Block]) -> RStyle:
        if element not in element_styles:
            element_styles[element] = element_style(doc, opts, element, block)
        base = element_styles[element]
        return RStyle(**base.__dict__)

    blocks: list[RBlock] = []
    for page_idx, b, dropped in flow:
        kind = b.type
        level = b.level
        if b.region == "__label__":
            kind, element = "region_label", "region"
        elif _bold_line_heading(b, opts):
            kind, level = "heading", min(max(opts.emphasis.bold_line_heading_level, 1), 4)
            element = f"h{level}"
        else:
            element = element_key(b)
        st = style_for(element, b)
        if b.font_category == "rashi":
            # Rashi script marks commentary, much like italics; it survives a change
            # of the main Hebrew font unless a different Rashi font is chosen.
            st.category = "rashi"
            st.font_hebrew = rashi_font(opts)
        st.direction = b.direction
        st.align = _align(b, element, opts) if kind != "region_label" else ("right" if b.direction == "rtl" else "left")
        st.indent = b.indent if kind not in ("heading", "figure") else 0.0
        if kind == "quote":
            st.indent = max(st.indent, 36.0)
            st.end_indent = 36.0
        if kind == "list_item":
            st.indent = max(st.indent, 18.0 + 18.0 * b.level)
        if kind in ("paragraph",) and element == "body":
            st.first_line = b.first_line_indent if opts.spacing.first_line_indent is None else opts.spacing.first_line_indent
        rb = RBlock(
            id=b.id,
            kind=kind,
            style=st,
            level=level,
            marker=b.list_marker,
            page=page_idx,
            source_ids=[b.id],
            dropped=dropped,
            continued=b.continued,
        )
        if kind == "table" and b.table is not None:
            rb.rows = [
                [RCell(runs=_runs(c.runs, b, st, opts, b.direction), colspan=c.colspan, rowspan=c.rowspan, header=c.header) for c in row]
                for row in b.table.rows
            ]
        elif kind == "figure" and b.figure is not None:
            img = b.figure.image or ""
            if img.startswith("data:"):
                rb.figure_src = img
            elif img and project_root is not None and (project_root / img).exists():
                rb.figure_src = str(project_root / img)
            rb.figure_width = max(0.15, min(b.figure.width_frac, 1.0))
            rb.figure_alt = b.figure.description
        else:
            rb.runs = _runs(b.runs, b, st, opts, b.direction)
        blocks.append(rb)

    w, h = _page_size(doc, opts)
    m = opts.page.margins
    ex = opts.extras
    body = style_for("body", None)
    rtl = doc.main_direction == "rtl"
    body.direction = doc.main_direction
    body.align = "right" if rtl else "left"
    first_heading = next((b.text.strip() for b in blocks if b.kind == "heading" and b.text.strip()), "")
    title = ex.title or first_heading or doc.title
    return RenderDoc(
        title=title,
        blocks=blocks,
        style=opts,
        direction=doc.main_direction,
        page_w=w,
        page_h=h,
        margins=(m.top, m.right, m.bottom, m.left),
        columns=max(1, min(opts.page.columns, 3)),
        background=opts.colors.page_background,
        accent=opts.colors.accent,
        accent_style=opts.colors.accent_style if opts.colors.accent else "none",
        link_color=opts.colors.link or "#1D4ED8",
        base=body,
        element_styles=element_styles,
        toc=ex.toc,
        toc_title=ex.toc_title or "Contents",
        page_numbers=ex.page_numbers,
        page_number_align=ex.page_number_align,
        title_page=ex.title_page,
        title_text=title,
        subtitle=ex.subtitle,
        author=ex.author,
        project_root=project_root,
    )
