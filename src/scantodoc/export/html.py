"""HTML export (also used for the live preview and as the source of the PDF).

The CSS is generated from the resolved styles; Hebrew-script runs get their
own font through a `.he` class, so a line can mix Times New Roman and
Frank Ruehl correctly.
"""

from __future__ import annotations

import base64
import html as H
import mimetypes
from pathlib import Path
from typing import Optional

from ..style import fonts as F
from ..style.resolve import RBlock, RenderDoc, RRun, RStyle, figure_bytes


def _esc(t: str) -> str:
    return H.escape(t, quote=True)


def _pt(v: float) -> str:
    return f"{round(v, 2):g}pt"


def element_css(cls: str, st: RStyle, rdoc: RenderDoc, scope: str = "") -> str:
    latin = F.css_family(st.stack(False))
    hebrew = F.css_family(st.stack(True))
    rules = [
        f"font-family:{latin}",
        f"font-size:{_pt(st.size)}",
        f"font-weight:{700 if st.bold else 400}",
        f"font-style:{'italic' if st.italic else 'normal'}",
        f"margin:{_pt(st.space_before)} 0 {_pt(st.space_after)} 0",
    ]
    if st.color:
        rules.append(f"color:{st.color}")
    if st.line_spacing:
        rules.append(f"line-height:{st.line_spacing * 1.15:.3f}")
    out = f"{scope}.{cls}{{{';'.join(rules)}}}\n{scope}.{cls} .he{{font-family:{hebrew}}}\n"
    if cls.startswith("e-h") and rdoc.accent:
        if rdoc.accent_style == "underline":
            out += f"{scope}.{cls}{{border-bottom:2px solid {rdoc.accent};padding-bottom:3pt}}\n"
        elif rdoc.accent_style == "rule":
            out += f"{scope}.{cls}{{border-bottom:0.75pt solid {rdoc.accent};padding-bottom:2pt}}\n"
        elif rdoc.accent_style == "bar":
            out += f"{scope}.{cls}{{border-inline-start:4pt solid {rdoc.accent};padding-inline-start:8pt}}\n"
    return out


def font_faces(rdoc: RenderDoc, font_mode: str = "embed", url_prefix: str = "/fonts/") -> str:
    """@font-face rules for the bundled fonts this document actually needs."""
    has_rtl = any(r.rtl for b in rdoc.blocks for r in b.runs) or any(
        r.rtl for b in rdoc.blocks for row in b.rows for c in row for r in c.runs
    )
    stacks = []
    for st in list(rdoc.element_styles.values()) + [rdoc.base]:
        stacks.append(st.stack(False))
        if has_rtl:
            stacks.append(st.stack(True))
    rashi = _rashi_style(rdoc)
    if rashi is not None:
        stacks.append(rashi.stack(True))
    return F.font_face_css(F.bundled_families_in(stacks), font_mode, url_prefix)


def _rashi_style(rdoc: RenderDoc) -> Optional[RStyle]:
    return next((b.style for b in rdoc.blocks if b.style.category == "rashi"), None)


def stylesheet(
    rdoc: RenderDoc, font_mode: str = "embed", url_prefix: str = "/fonts/", scope: str = "", with_faces: bool = True
) -> str:
    rashi = _rashi_style(rdoc)
    faces = font_faces(rdoc, font_mode, url_prefix) if with_faces else ""
    css = [faces]
    base = rdoc.base
    css.append(
        f"{scope}.doc{{font-family:{F.css_family(base.stack(False))};font-size:{_pt(base.size)};"
        f"line-height:{(base.line_spacing or 1.0) * 1.15:.3f};color:#111;"
        f"{'column-count:%d;column-gap:0.35in;' % rdoc.columns if rdoc.columns > 1 else ''}}}"
    )
    css.append(f"{scope}.doc .he{{font-family:{F.css_family(base.stack(True))}}}")
    for element, st in rdoc.element_styles.items():
        css.append(element_css(f"e-{element}", st, rdoc, scope))
    if rashi is not None:
        css.append(f"{scope}.doc .rashi .he,{scope}.doc .rashi.he{{font-family:{F.css_family(rashi.stack(True))}}}")
    css.append(
        f"""{scope}.doc p,{scope}.doc h1,{scope}.doc h2,{scope}.doc h3,{scope}.doc h4{{orphans:2;widows:2}}
{scope}.doc h1,{scope}.doc h2,{scope}.doc h3,{scope}.doc h4{{break-after:avoid;line-height:1.2}}
{scope}.doc .li{{display:block}}
{scope}.doc .mk{{display:inline-block;min-width:1.4em}}
{scope}.doc table{{border-collapse:collapse;margin-left:auto;margin-right:auto;max-width:100%;break-inside:auto}}
{scope}.doc td,{scope}.doc th{{border:0.75pt solid #555;padding:3pt 6pt;vertical-align:top;text-align:start}}
{scope}.doc th{{font-weight:700}}
{scope}.doc figure{{margin:8pt auto;text-align:center;break-inside:avoid}}
{scope}.doc figure img{{max-width:100%;height:auto}}
{scope}.doc a{{color:{rdoc.link_color}}}
{scope}.doc .e-region{{font-weight:700;letter-spacing:0.03em;border-bottom:0.5pt solid #999;padding-bottom:2pt}}
{scope}.doc .toc ol{{list-style:none;padding:0;margin:0}}
{scope}.doc .toc li{{margin:2pt 0}}
{scope}.doc .toc a{{color:inherit;text-decoration:none}}
{scope}.doc .title-page{{text-align:center;padding-top:2.5in;break-after:page;column-span:all}}
{scope}.doc .title-page .t{{font-size:28pt;font-weight:700;margin-bottom:14pt}}
{scope}.doc .title-page .s{{font-size:16pt;margin-bottom:28pt}}
{scope}.doc .title-page .a{{font-size:13pt}}
{scope}.doc .toc{{break-after:page;column-span:all}}"""
    )
    if rdoc.style.extras.highlight_uncertain:
        css.append(f"{scope}.doc .unc{{background:#FFF3A3}}")
    return "\n".join(css)


def run_html(r: RRun, base_dir: str) -> str:
    text = _esc(r.text)
    if r.superscript:
        text = f"<sup>{text}</sup>"
    elif r.subscript:
        text = f"<sub>{text}</sub>"
    if r.bold:
        text = f"<b>{text}</b>"
    if r.italic:
        text = f"<i>{text}</i>"
    if r.underline and not r.link:
        text = f"<u>{text}</u>"
    if r.strike:
        text = f"<s>{text}</s>"
    if r.link:
        text = f'<a href="{_esc(r.link)}">{text}</a>'
    attrs = []
    classes = []
    if r.rtl:
        classes.append("he")
    if r.uncertain:
        classes.append("unc")
        if r.confidence is not None:
            attrs.append(f'title="Confidence {r.confidence:.0f}%"')
    style = f' style="color:{r.color}"' if r.color else ""
    run_dir = "rtl" if r.rtl else "ltr"
    if run_dir != base_dir:
        attrs.append(f'dir="{run_dir}"')
    if classes:
        attrs.insert(0, f'class="{" ".join(classes)}"')
    if attrs or style:
        return f"<span {' '.join(attrs)}{style}>{text}</span>".replace("<span >", "<span>")
    return text


def _block_style(b: RBlock) -> str:
    st = b.style
    css = [f"text-align:{st.align}"]
    if st.indent:
        css.append(f"margin-inline-start:{_pt(st.indent)}")
    if st.end_indent:
        css.append(f"margin-inline-end:{_pt(st.end_indent)}")
    if st.first_line:
        css.append(f"text-indent:{_pt(st.first_line)}")
    return ";".join(css)


def _img_src(src: Optional[str], embed: bool) -> Optional[str]:
    if not src:
        return None
    if src.startswith("data:"):
        return src
    if not embed:
        return Path(src).as_uri()
    data = figure_bytes(src)
    if data is None:
        return None
    mime = mimetypes.guess_type(src)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def block_html(b: RBlock, embed_images: bool = True, preview: bool = False, img_url=None) -> str:
    st = b.style
    d = st.direction
    data = f' data-id="{b.id}" data-kind="{b.kind}"' if preview else ""
    if preview and b.dropped:
        data += ' data-dropped="1"'
    cls_extra = " dropped" if b.dropped else ""
    if st.category == "rashi":
        cls_extra += " rashi"
    runs = "".join(run_html(r, d) for r in b.runs)
    style = _block_style(b)
    if b.kind == "heading":
        lvl = min(max(b.level, 1), 4)
        return f'<h{lvl} id="h-{b.id}" class="e-h{lvl}{cls_extra}" dir="{d}" style="{style}"{data}>{runs}</h{lvl}>'
    if b.kind == "list_item":
        marker = _esc(b.marker or "•")
        hang = "1.4em"
        return (
            f'<p class="e-list li{cls_extra}" dir="{d}" style="{style};text-indent:-{hang};padding-inline-start:{hang}"{data}>'
            f'<span class="mk" contenteditable="false">{marker}</span>{runs}</p>'
        )
    if b.kind == "table":
        rows = []
        for row in b.rows:
            cells = []
            for c in row:
                tag = "th" if c.header else "td"
                span = (f' colspan="{c.colspan}"' if c.colspan > 1 else "") + (f' rowspan="{c.rowspan}"' if c.rowspan > 1 else "")
                cells.append(f"<{tag}{span}>{''.join(run_html(r, d) for r in c.runs)}</{tag}>")
            rows.append("<tr>" + "".join(cells) + "</tr>")
        return f'<table class="e-table{cls_extra}" dir="{d}"{data}>{"".join(rows)}</table>'
    if b.kind == "figure":
        src = img_url(b) if img_url else _img_src(b.figure_src, embed_images)
        if not src:
            return ""
        alt = _esc(b.figure_alt)
        return f'<figure class="fig{cls_extra}"{data}><img src="{src}" alt="{alt}" style="width:{b.figure_width * 100:.0f}%"></figure>'
    if b.kind == "region_label":
        return f'<p class="e-region" dir="{d}" style="{style}"{data}>{runs}</p>'
    element = st.element if st.element in ("caption", "footnote", "quote", "header", "footer") else "body"
    if b.kind == "page_number":
        element = "footer"
    tag = "blockquote" if b.kind == "quote" else "p"
    return f'<{tag} class="e-{element}{cls_extra}" dir="{d}" style="{style}"{data}>{runs}</{tag}>'


def toc_html(rdoc: RenderDoc) -> str:
    items = []
    for h in rdoc.headings():
        pad = (min(max(h.level, 1), 4) - 1) * 14
        items.append(f'<li style="padding-inline-start:{pad}pt"><a href="#h-{h.id}">{_esc(h.text)}</a></li>')
    return f'<nav class="toc" dir="{rdoc.direction}"><h2 class="e-h2">{_esc(rdoc.toc_title)}</h2><ol>{"".join(items)}</ol></nav>'


def title_html(rdoc: RenderDoc) -> str:
    parts = [f'<div class="t">{_esc(rdoc.title_text)}</div>']
    if rdoc.subtitle:
        parts.append(f'<div class="s">{_esc(rdoc.subtitle)}</div>')
    if rdoc.author:
        parts.append(f'<div class="a">{_esc(rdoc.author)}</div>')
    return f'<section class="title-page" dir="{rdoc.direction}">{"".join(parts)}</section>'


def body_html(rdoc: RenderDoc, embed_images: bool = True) -> str:
    out = []
    if rdoc.title_page:
        out.append(title_html(rdoc))
    if rdoc.toc and rdoc.headings():
        out.append(toc_html(rdoc))
    out += [block_html(b, embed_images) for b in rdoc.blocks if not b.dropped]
    return "\n".join(out)


def page_css(rdoc: RenderDoc) -> str:
    t, r, b, l_ = rdoc.margins
    css = f"@page{{size:{rdoc.page_w}in {rdoc.page_h}in;margin:{t}in {r}in {b}in {l_}in;"
    if rdoc.page_numbers:
        align = {"center": "bottom-center", "left": "bottom-left", "right": "bottom-right"}[rdoc.page_number_align]
        css += f"@{align}{{content:counter(page);font-family:{F.css_family(rdoc.base.stack(False))};font-size:9pt;color:#444}}"
    css += "}"
    if rdoc.title_page and rdoc.page_numbers:
        css += "@page:first{@bottom-center{content:none}@bottom-left{content:none}@bottom-right{content:none}}"
    return css


def render_html(rdoc: RenderDoc, font_mode: str = "embed", embed_images: bool = True, for_print: bool = False) -> str:
    """A complete, standalone HTML document."""
    bg = rdoc.background or "#FFFFFF"
    screen = (
        f"html{{background:#E9E7E2}}body{{margin:0;padding:24px 12px}}"
        f".sheet{{background:{bg};max-width:{rdoc.page_w}in;margin:0 auto;box-sizing:border-box;"
        f"padding:{rdoc.margins[0]}in {rdoc.margins[1]}in {rdoc.margins[2]}in {rdoc.margins[3]}in;"
        f"box-shadow:0 1px 6px rgba(0,0,0,.15)}}"
        f"@media (max-width:700px){{.sheet{{padding:24px 16px}}}}"
    )
    printing = f"html,body{{margin:0;padding:0;background:{bg}}}" + page_css(rdoc)
    head = (
        '<!doctype html><html lang="{lang}" dir="{d}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>{title}</title><style>{css}\n{extra}\n@media print{{{printing}.sheet{{box-shadow:none;padding:0;max-width:none}}}}</style></head>"
    ).format(
        lang="he" if rdoc.direction == "rtl" else "en",
        d=rdoc.direction,
        title=_esc(rdoc.title or "Document"),
        css=stylesheet(rdoc, font_mode),
        extra=printing if for_print else screen,
        printing=page_css(rdoc) if not for_print else "",
    )
    return f'{head}<body><div class="sheet"><div class="doc" dir="{rdoc.direction}">{body_html(rdoc, embed_images)}</div></div></body></html>'


def preview_html(rdoc: RenderDoc, img_url=None) -> dict:
    """Pieces for the web app's live preview: CSS (scoped) and HTML per page."""
    css = stylesheet(rdoc, scope="", with_faces=False)
    pages: dict[int, list[str]] = {}
    for b in rdoc.blocks:
        pages.setdefault(b.page, []).append(block_html(b, embed_images=False, preview=True, img_url=img_url))
    front = []
    if rdoc.title_page:
        front.append(title_html(rdoc))
    if rdoc.toc and rdoc.headings():
        front.append(toc_html(rdoc))
    return {
        "fonts": font_faces(rdoc, "url", "/fonts/"),
        "css": css,
        "front": "\n".join(front),
        "pages": {str(k): "\n".join(v) for k, v in pages.items()},
        "direction": rdoc.direction,
        "page_w": rdoc.page_w,
        "page_h": rdoc.page_h,
        "margins": rdoc.margins,
        "background": rdoc.background or "#FFFFFF",
        "columns": rdoc.columns,
    }
