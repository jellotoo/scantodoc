"""Word (.docx) export.

Uses Word's own styles - Normal, Heading 1-4, Title, Quote, Caption, List -
so the navigation pane, outline view and automatic table of contents all
work. Each style carries two fonts: one for Latin text and one for Hebrew
("complex script") text, exactly as Word itself stores them.

A detail worth knowing: in a right-to-left paragraph, Word's "left" and
"right" alignment values mean start and end, so a right-aligned Hebrew
paragraph is written as jc="left". Indents are likewise start/end.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Optional

from docx import Document as new_docx
from docx.enum.section import WD_ORIENT
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_BREAK
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from PIL import Image

from ..style.resolve import RBlock, RenderDoc, RRun, RStyle, figure_bytes

RPR_ORDER = [
    "rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike", "dstrike", "outline", "shadow",
    "emboss", "imprint", "noProof", "snapToGrid", "vanish", "webHidden", "color", "spacing", "w", "kern",
    "position", "sz", "szCs", "highlight", "u", "effect", "bdr", "shd", "fitText", "vertAlign", "rtl", "cs",
    "em", "lang", "eastAsianLayout", "specVanish", "oMath",
]
PPR_ORDER = [
    "pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr", "widowControl", "numPr",
    "suppressLineNumbers", "pBdr", "shd", "tabs", "suppressAutoHyphens", "kinsoku", "wordWrap",
    "overflowPunct", "topLinePunct", "autoSpaceDE", "autoSpaceDN", "bidi", "adjustRightInd", "snapToGrid",
    "spacing", "ind", "contextualSpacing", "mirrorIndents", "suppressOverlap", "jc", "textDirection",
    "textAlignment", "textboxTightWrap", "outlineLvl", "divId", "cnfStyle", "rPr", "sectPr", "pPrChange",
]
SECTPR_ORDER = [
    "headerReference", "footerReference", "footnotePr", "endnotePr", "type", "pgSz", "pgMar", "paperSrc",
    "pgBorders", "lnNumType", "pgNumType", "cols", "formProt", "vAlign", "noEndnote", "titlePg",
    "textDirection", "bidi", "rtlGutter", "docGrid", "printerSettings", "sectPrChange",
]
STYLE_NAMES = {
    "body": "Normal", "h1": "Heading 1", "h2": "Heading 2", "h3": "Heading 3", "h4": "Heading 4",
    "list": "List Paragraph", "quote": "Quote", "caption": "Caption", "footnote": "ScanToDoc Footnote",
    "table": "ScanToDoc Table Text", "header": "ScanToDoc Running Head", "footer": "ScanToDoc Running Head",
    "region": "ScanToDoc Region Label",
}


def _set_child(parent, tag: str, order: list[str], attrs: Optional[dict] = None, remove: bool = False):
    """Create/replace a child element keeping the schema's required order."""
    q = qn(f"w:{tag}")
    for old in parent.findall(q):
        parent.remove(old)
    if remove:
        return None
    el = OxmlElement(f"w:{tag}")
    for k, v in (attrs or {}).items():
        el.set(qn(f"w:{k}"), str(v))
    idx = order.index(tag)
    for i, child in enumerate(list(parent)):
        name = child.tag.split("}")[-1]
        if name in order and order.index(name) > idx:
            child.addprevious(el)
            return el
    parent.append(el)
    return el


def _hex(c: Optional[str]) -> Optional[str]:
    return c[1:].upper() if c else None


# ---------------------------------------------------------------- styles


def _style(doc, name: str, kind=WD_STYLE_TYPE.PARAGRAPH, base: str = "Normal"):
    try:
        return doc.styles[name]
    except KeyError:
        st = doc.styles.add_style(name, kind)
        if kind == WD_STYLE_TYPE.PARAGRAPH:
            st.base_style = doc.styles[base]
            st.quick_style = True
        return st


def _apply_style(style, st: RStyle, accent: Optional[str], accent_style: str, heading: bool) -> None:
    font = style.font
    font.name = st.font_latin
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = _set_child(rpr, "rFonts", RPR_ORDER)
    for att in ("ascii", "hAnsi", "eastAsia"):
        rfonts.set(qn(f"w:{att}"), st.font_latin)
    rfonts.set(qn("w:cs"), st.font_hebrew)
    for theme in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
        if rfonts.get(qn(f"w:{theme}")) is not None:
            del rfonts.attrib[qn(f"w:{theme}")]
    font.size = Pt(st.size)
    _set_child(rpr, "szCs", RPR_ORDER, {"val": int(round(st.size * 2))})
    font.bold = st.bold
    _set_child(rpr, "bCs", RPR_ORDER, {"val": "1" if st.bold else "0"})
    font.italic = st.italic
    _set_child(rpr, "iCs", RPR_ORDER, {"val": "1" if st.italic else "0"})
    # Word's built-in styles bring their own colours (blue captions, grey
    # quotes); the detected or chosen colour always wins, black otherwise.
    font.color.rgb = RGBColor.from_string(_hex(st.color)) if st.color else RGBColor(0, 0, 0)
    pf = style.paragraph_format
    pf.space_before = Pt(st.space_before)
    pf.space_after = Pt(st.space_after)
    if st.line_spacing:
        pf.line_spacing = st.line_spacing
    if heading:
        pf.keep_with_next = True
        if accent and accent_style in ("underline", "rule"):
            ppr = style.element.get_or_add_pPr()
            bdr = _set_child(ppr, "pBdr", PPR_ORDER)
            bottom = OxmlElement("w:bottom")
            bottom.set(qn("w:val"), "single")
            bottom.set(qn("w:sz"), "12" if accent_style == "underline" else "6")
            bottom.set(qn("w:space"), "2")
            bottom.set(qn("w:color"), _hex(accent))
            bdr.append(bottom)
        elif accent and accent_style == "bar":
            ppr = style.element.get_or_add_pPr()
            bdr = _set_child(ppr, "pBdr", PPR_ORDER)
            side = OxmlElement("w:left")
            side.set(qn("w:val"), "single")
            side.set(qn("w:sz"), "24")
            side.set(qn("w:space"), "8")
            side.set(qn("w:color"), _hex(accent))
            bdr.append(side)


def setup_styles(doc, rdoc: RenderDoc) -> None:
    _apply_style(doc.styles["Normal"], rdoc.base, None, "none", False)
    for element, st in rdoc.element_styles.items():
        name = STYLE_NAMES.get(element)
        if not name:
            continue
        style = _style(doc, name)
        _apply_style(style, st, rdoc.accent, rdoc.accent_style, element.startswith("h") and len(element) == 2)
    link = _style(doc, "Hyperlink", WD_STYLE_TYPE.CHARACTER)
    link.font.color.rgb = RGBColor.from_string(_hex(rdoc.link_color))
    link.font.underline = True


# ---------------------------------------------------------------- runs & paragraphs


def _add_run(par, r: RRun, st: RStyle, highlight: bool, doc, hebrew_font: Optional[str] = None) -> None:
    if r.link:
        rel = par.part.relate_to(r.link, RT.HYPERLINK, is_external=True)
        hl = OxmlElement("w:hyperlink")
        hl.set(qn("r:id"), rel)
        par._p.append(hl)
        run_el = OxmlElement("w:r")
        hl.append(run_el)
        from docx.text.run import Run as DocxRun

        run = DocxRun(run_el, par)
        run.text = r.text
        rpr = run._r.get_or_add_rPr()
        _set_child(rpr, "rStyle", RPR_ORDER, {"val": "Hyperlink"})
    else:
        run = par.add_run(r.text)
        rpr = run._r.get_or_add_rPr()
    if r.bold != st.bold:
        run.bold = r.bold
        _set_child(rpr, "bCs", RPR_ORDER, {"val": "1" if r.bold else "0"})
    if r.italic != st.italic:
        run.italic = r.italic
        _set_child(rpr, "iCs", RPR_ORDER, {"val": "1" if r.italic else "0"})
    if r.underline and not r.link:
        run.underline = True
    if r.strike:
        run.font.strike = True
    if r.color and r.color != st.color:
        run.font.color.rgb = RGBColor.from_string(_hex(r.color))
    if r.superscript:
        run.font.superscript = True
    elif r.subscript:
        run.font.subscript = True
    if highlight and r.uncertain:
        _set_child(rpr, "highlight", RPR_ORDER, {"val": "yellow"})
    if hebrew_font:
        _set_child(rpr, "rFonts", RPR_ORDER, {"cs": hebrew_font})
    if r.rtl:
        _set_child(rpr, "rtl", RPR_ORDER)
        _set_child(rpr, "lang", RPR_ORDER, {"bidi": "he-IL"})


def _para_format(par, st: RStyle) -> None:
    ppr = par._p.get_or_add_pPr()
    rtl = st.direction == "rtl"
    if rtl:
        _set_child(ppr, "bidi", PPR_ORDER)
    align = st.align
    if rtl and align in ("left", "right"):
        align = "right" if align == "left" else "left"  # start/end semantics in RTL paragraphs
    jc = {"left": "left", "right": "right", "center": "center", "justify": "both"}[align]
    _set_child(ppr, "jc", PPR_ORDER, {"val": jc})
    ind = {}
    if st.indent:
        ind["left"] = int(st.indent * 20)  # "left" is the start side, also in RTL paragraphs
    if st.end_indent:
        ind["right"] = int(st.end_indent * 20)
    if st.first_line > 0:
        ind["firstLine"] = int(st.first_line * 20)
    elif st.first_line < 0:
        ind["hanging"] = int(-st.first_line * 20)
    if ind:
        _set_child(ppr, "ind", PPR_ORDER, ind)


def _paragraph(doc, container, b: RBlock, rdoc: RenderDoc):
    st = b.style
    element = st.element
    if b.kind == "heading":
        name = f"Heading {min(max(b.level, 1), 4)}"
    elif b.kind == "page_number":
        name = STYLE_NAMES["footer"]
    elif b.kind == "region_label":
        name = STYLE_NAMES["region"]
    else:
        name = STYLE_NAMES.get(element, "Normal")
    par = container.add_paragraph(style=name)
    _para_format(par, st)
    highlight = rdoc.style.extras.highlight_uncertain
    if b.kind == "list_item":
        marker = b.marker or "•"
        mk = RRun(text=marker + "\t", rtl=st.direction == "rtl" and not marker.isascii())
        _add_run(par, mk, st, False, doc)
        ppr = par._p.get_or_add_pPr()
        start = int((st.indent or 18) * 20)
        _set_child(ppr, "ind", PPR_ORDER, {"left": start, "hanging": 360})
        tabs = _set_child(ppr, "tabs", PPR_ORDER)
        tab = OxmlElement("w:tab")
        tab.set(qn("w:val"), "left")
        tab.set(qn("w:pos"), str(start))
        tabs.append(tab)
    element_font = rdoc.element_styles.get(st.element, rdoc.base).font_hebrew
    override = st.font_hebrew if st.font_hebrew != element_font else None
    for r in b.runs:
        _add_run(par, r, st, highlight, doc, override)
    if b.kind == "heading":
        _bookmark(par, f"h{b.id}")
    return par


def _bookmark(par, name: str) -> None:
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(abs(hash(name)) % 10_000_000))
    start.set(qn("w:name"), name[:40])
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), start.get(qn("w:id")))
    par._p.insert(1 if par._p.pPr is not None else 0, start)
    par._p.append(end)


def _table(doc, b: RBlock, rdoc: RenderDoc) -> None:
    rows = b.rows
    if not rows:
        return
    ncols = max(sum(c.colspan for c in row) for row in rows)
    table = doc.add_table(rows=len(rows), cols=ncols)
    try:
        table.style = doc.styles["Table Grid"]
    except KeyError:
        pass
    st = b.style
    tblPr = table._tbl.tblPr
    if st.direction == "rtl":
        el = OxmlElement("w:bidiVisual")
        tblPr.append(el)
    taken = [[False] * ncols for _ in rows]
    for r_i, row in enumerate(rows):
        c_i = 0
        for cell in row:
            while c_i < ncols and taken[r_i][c_i]:
                c_i += 1
            if c_i >= ncols:
                break
            end_c = min(c_i + cell.colspan - 1, ncols - 1)
            end_r = min(r_i + cell.rowspan - 1, len(rows) - 1)
            target = table.cell(r_i, c_i)
            if end_c > c_i or end_r > r_i:
                target = target.merge(table.cell(end_r, end_c))
            for rr in range(r_i, end_r + 1):
                for cc in range(c_i, end_c + 1):
                    taken[rr][cc] = True
            par = target.paragraphs[0]
            par.style = _style(doc, STYLE_NAMES["table"])
            cst = RStyle(**{**st.__dict__, "align": "right" if st.direction == "rtl" else "left", "indent": 0.0, "first_line": 0.0})
            _para_format(par, cst)
            for r in cell.runs:
                rr_ = RRun(**{**r.__dict__, "bold": r.bold or cell.header})
                _add_run(par, rr_, cst, rdoc.style.extras.highlight_uncertain, doc)
            c_i = end_c + 1
        if any(c.header for c in row) and r_i == 0:
            trPr = table.rows[0]._tr.get_or_add_trPr()
            hdr = OxmlElement("w:tblHeader")
            trPr.append(hdr)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def _figure(doc, b: RBlock, rdoc: RenderDoc) -> None:
    data = figure_bytes(b.figure_src)
    if not data:
        return
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.load()
            if im.mode not in ("RGB", "L", "RGBA", "P"):
                im = im.convert("RGB")
            buf = io.BytesIO()
            im.save(buf, format="PNG")
            data = buf.getvalue()
    except Exception:  # noqa: BLE001 - an unreadable picture is skipped
        return
    width = Inches(max(0.5, rdoc.text_width / max(rdoc.columns, 1) * b.figure_width))
    par = doc.add_paragraph()
    par.alignment = 1
    par.add_run().add_picture(io.BytesIO(data), width=width)
    if b.figure_alt:
        docpr = par._p.xpath(".//wp:docPr")
        if docpr:
            docpr[0].set("descr", b.figure_alt)


# ---------------------------------------------------------------- document-level parts


def _field(par, instr: str, placeholder: str = "") -> None:
    """A Word field (PAGE, TOC ...) as begin/instr/separate/result/end runs."""

    def fld(kind: str, dirty: bool = False):
        r = OxmlElement("w:r")
        f = OxmlElement("w:fldChar")
        f.set(qn("w:fldCharType"), kind)
        if dirty:
            f.set(qn("w:dirty"), "true")
        r.append(f)
        return r

    p = par._p
    p.append(fld("begin", dirty=instr.strip().startswith("TOC")))
    r = OxmlElement("w:r")
    t = OxmlElement("w:instrText")
    t.set(qn("xml:space"), "preserve")
    t.text = f" {instr} "
    r.append(t)
    p.append(r)
    p.append(fld("separate"))
    if placeholder:
        r = OxmlElement("w:r")
        tt = OxmlElement("w:t")
        tt.set(qn("xml:space"), "preserve")
        tt.text = placeholder
        r.append(tt)
        p.append(r)
    p.append(fld("end"))


def _page_numbers(section, rdoc: RenderDoc) -> None:
    footer = section.footer
    footer.is_linked_to_previous = False
    par = footer.paragraphs[0]
    par.alignment = {"center": 1, "left": 0, "right": 2}[rdoc.page_number_align]
    if rdoc.direction == "rtl":
        _set_child(par._p.get_or_add_pPr(), "bidi", PPR_ORDER)
    _field(par, "PAGE", "1")
    for r_el in par._p.findall(qn("w:r")):
        rpr = r_el.find(qn("w:rPr"))
        if rpr is None:
            rpr = OxmlElement("w:rPr")
            r_el.insert(0, rpr)
        _set_child(rpr, "b", RPR_ORDER, {"val": "0"})
        _set_child(rpr, "sz", RPR_ORDER, {"val": 18})


def _toc(doc, rdoc: RenderDoc) -> None:
    """A real Word table of contents. Its entries are filled in already, so it
    shows straight away; Word adds the page numbers when it updates fields on
    opening (it may ask "update fields?" - answer Yes)."""
    head = doc.add_paragraph(rdoc.toc_title, style=_toc_heading_style(doc))
    if rdoc.direction == "rtl":
        _set_child(head._p.get_or_add_pPr(), "bidi", PPR_ORDER)
    heads = rdoc.headings()
    for lvl in range(1, 5):
        st = _style(doc, f"TOC {lvl}")
        st.paragraph_format.left_indent = Pt(14 * (lvl - 1))
        st.paragraph_format.space_after = Pt(2)
    entries = heads or []
    if not entries:
        return
    for i, h in enumerate(entries):
        par = doc.add_paragraph(style=f"TOC {min(max(h.level, 1), 4)}")
        if h.style.direction == "rtl":
            _set_child(par._p.get_or_add_pPr(), "bidi", PPR_ORDER)
        if i == 0:
            _field_begin(par, 'TOC \\o "1-4" \\h \\z \\u')
        for r in h.runs:
            _add_run(par, RRun(**{**r.__dict__, "bold": False, "color": None, "link": None}), h.style, False, doc)
        if i == len(entries) - 1:
            _field_end(par)
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def _field_begin(par, instr: str) -> None:
    p = par._p
    for kind, text in (("begin", None), (None, instr), ("separate", None)):
        r = OxmlElement("w:r")
        if kind:
            f = OxmlElement("w:fldChar")
            f.set(qn("w:fldCharType"), kind)
            if kind == "begin":
                f.set(qn("w:dirty"), "true")
            r.append(f)
        else:
            t = OxmlElement("w:instrText")
            t.set(qn("xml:space"), "preserve")
            t.text = f" {text} "
            r.append(t)
        p.append(r)


def _field_end(par) -> None:
    r = OxmlElement("w:r")
    f = OxmlElement("w:fldChar")
    f.set(qn("w:fldCharType"), "end")
    r.append(f)
    par._p.append(r)


def _toc_heading_style(doc) -> str:
    st = _style(doc, "TOC Heading")
    st.font.size = Pt(16)
    st.font.bold = True
    return "TOC Heading"


def _title_page(doc, rdoc: RenderDoc) -> None:
    rtl = rdoc.direction == "rtl"
    h1 = rdoc.element_styles.get("h1", rdoc.base)
    for name, size in (("Title", 28), ("Subtitle", 16)):
        st = RStyle(**{**h1.__dict__, "size": size, "bold": name == "Title", "space_before": 0, "space_after": 12})
        style = _style(doc, name)
        _apply_style(style, st, None, "none", False)
        ppr = style.element.get_or_add_pPr()
        _set_child(ppr, "pBdr", PPR_ORDER, remove=True)
    for _ in range(6):
        doc.add_paragraph()
    for text, size, bold in ((rdoc.title_text, 28, True), (rdoc.subtitle, 16, False), (rdoc.author, 13, False)):
        if not text:
            continue
        p = doc.add_paragraph(style="Title" if size == 28 else "Subtitle" if size == 16 else "Normal")
        p.alignment = 1
        if rtl:
            _set_child(p._p.get_or_add_pPr(), "bidi", PPR_ORDER)
        run = p.add_run(text)
        run.font.size = Pt(size)
        run.bold = bold
        if rtl:
            _set_child(run._r.get_or_add_rPr(), "rtl", RPR_ORDER)
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def _section_setup(doc, rdoc: RenderDoc) -> None:
    sec = doc.sections[0]
    w, h = rdoc.page_w, rdoc.page_h
    sec.orientation = WD_ORIENT.LANDSCAPE if w > h else WD_ORIENT.PORTRAIT
    sec.page_width, sec.page_height = Inches(w), Inches(h)
    t, r, b, l_ = rdoc.margins
    sec.top_margin, sec.right_margin, sec.bottom_margin, sec.left_margin = Inches(t), Inches(r), Inches(b), Inches(l_)
    sectPr = sec._sectPr
    if rdoc.columns > 1:
        _set_child(sectPr, "cols", SECTPR_ORDER, {"num": rdoc.columns, "space": 504})
    if rdoc.direction == "rtl":
        _set_child(sectPr, "bidi", SECTPR_ORDER)
    if rdoc.title_page:
        _set_child(sectPr, "titlePg", SECTPR_ORDER)
    if rdoc.page_numbers:
        _page_numbers(sec, rdoc)


def _background(doc, color: str) -> None:
    body = doc.element
    bg = OxmlElement("w:background")
    bg.set(qn("w:color"), _hex(color))
    body.insert(0, bg)
    settings = doc.settings.element
    disp = OxmlElement("w:displayBackgroundShape")
    settings.insert(0, disp)


def _update_fields_on_open(doc) -> None:
    settings = doc.settings.element
    el = OxmlElement("w:updateFields")
    el.set(qn("w:val"), "true")
    settings.append(el)


def render_docx(rdoc: RenderDoc) -> bytes:
    doc = new_docx()
    setup_styles(doc, rdoc)
    _section_setup(doc, rdoc)
    if rdoc.background:
        _background(doc, rdoc.background)
    cp = doc.core_properties
    cp.title = rdoc.title or ""
    cp.author = rdoc.author or "ScanToDoc"
    cp.comments = "Converted from a scan with ScanToDoc"
    if rdoc.title_page:
        _title_page(doc, rdoc)
    if rdoc.toc and rdoc.headings():
        _toc(doc, rdoc)
        _update_fields_on_open(doc)
    # The default template starts with one empty paragraph; reuse nothing from it.
    for b in rdoc.blocks:
        if b.dropped:
            continue
        if b.kind == "table":
            _table(doc, b, rdoc)
        elif b.kind == "figure":
            _figure(doc, b, rdoc)
        else:
            _paragraph(doc, doc, b, rdoc)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def write_docx(rdoc: RenderDoc, path: Path) -> Path:
    path.write_bytes(render_docx(rdoc))
    return path

