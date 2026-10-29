"""Build the sample "scanned" pages used by the tests.

Each sample is described below as a list of pages of blocks (the answer key).
The blocks are rendered to HTML, photographed at 300 DPI with headless
Chromium, roughened a little to look like a scan, and saved as an image-only
PDF. The answer key is saved next to it as JSON in the same shape the Claude
reader asks Claude for, with each block's position measured from the page.

Run from the scantodoc folder:  python tests/samples/build_samples.py
The generated files are committed, so the tests do not need a browser.
"""

from __future__ import annotations

import html
import io
import json
import random
import sys
from pathlib import Path

import pymupdf
from PIL import Image, ImageFilter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scantodoc.browser import chromium  # noqa: E402

FONTS = ROOT / "src" / "scantodoc" / "fonts"
DPI = 300
PAGE_W_IN, PAGE_H_IN = 8.5, 11.0

NAVY = "#1F3A5F"
RED = "#C0392B"
GREEN = "#1E7B34"


def R(text, **fmt):
    run = {"text": text}
    run.update(fmt)
    return run


def B(type_, runs, **kw):
    block = {"type": type_, "runs": runs}
    block.update(kw)
    return block


# ---------------------------------------------------------------- english (2 pages)
ENGLISH = [
    [
        B("header", [R("ScanToDoc Sample Report — Chapter One")], size=9, align="center", font="serif"),
        B("heading", [R("A Short History of Printing", bold=True, color=NAVY)], level=1, size=24, align="center"),
        B(
            "paragraph",
            [
                R("The invention of movable type changed how knowledge travelled. Before it, every book was copied by hand, and a "),
                R("single", bold=True),
                R(" mistake could pass from copy to copy for centuries. Printers could now set a page once and print it "),
                R("hundreds of times", italic=True),
                R(", which made books cheaper and far more "),
                R("consistent", underline=True),
                R("."),
            ],
            size=12,
            align="justify",
        ),
        B("heading", [R("Early Presses", bold=True, color=NAVY)], level=2, size=17),
        B(
            "paragraph",
            [
                R("Early presses were made of wood and worked like a wine press. A skilled team could print a few hundred sheets a day. "),
                R("Ink was mixed by hand from soot and varnish", color=RED),
                R(", and paper was dampened before printing so that it took the ink evenly."),
            ],
            size=12,
            align="justify",
        ),
        B("list_item", [R("Gutenberg Bible, about 1455")], size=12, marker="•", level=0),
        B("list_item", [R("Soncino Hebrew Bible, 1488")], size=12, marker="•", level=0),
        B("list_item", [R("Aldine editions of the classics, from 1495")], size=12, marker="•", level=0),
        B("heading", [R("Why It Mattered", bold=True, color=NAVY)], level=2, size=17),
        B(
            "paragraph",
            [
                R("Printed books spread new ideas quickly. Scholars in different cities could finally refer to the same page of the same "),
                R("edition, and errors could be corrected in the next printing rather than"),
            ],
            size=12,
            align="justify",
            continues=True,
        ),
        B("footer", [R("1")], size=10, align="center"),
    ],
    [
        B("header", [R("ScanToDoc Sample Report — Chapter One")], size=9, align="center", font="serif"),
        B(
            "paragraph",
            [R("copied forward forever. This simple change is one reason the period is called a revolution.")],
            size=12,
            align="justify",
            continued=True,
        ),
        B("heading", [R("Steps in Setting a Page", bold=True, color=NAVY)], level=2, size=17),
        B("list_item", [R("Pick each letter from the type case.")], size=12, marker="1.", level=0),
        B("list_item", [R("Lock the lines into a frame called a chase.")], size=12, marker="2.", level=0),
        B("list_item", [R("Ink the type and pull the press.")], size=12, marker="3.", level=0),
        B(
            "quote",
            [R("“What the printing press did for books, the scanner can do again for old books.”", italic=True)],
            size=12,
            align="left",
            indent=36,
        ),
        B(
            "paragraph",
            [
                R("Modern readers can reach the same books in seconds. Water has the formula H"),
                R("2", subscript=True),
                R("O, and Einstein wrote E = mc"),
                R("2", superscript=True),
                R("; even such small details should survive conversion."),
            ],
            size=12,
            align="justify",
        ),
        B("footnote", [R("1 Dates are approximate and vary between sources.")], size=9, align="left"),
        B("footer", [R("2")], size=10, align="center"),
    ],
]

# ---------------------------------------------------------------- hebrew + english (1 page)
HEBREW = [
    [
        B("heading", [R("פרק ראשון: הקדמה", bold=True, color=NAVY)], level=1, size=22, align="center", dir="rtl"),
        B(
            "paragraph",
            [
                R("זהו דף לדוגמה הכתוב בעברית. המילה "),
                R("חשובה", bold=True),
                R(" מודגשת, ויש כאן גם מילים באנגלית כמו Rashi ו-Rambam בתוך השורה."),
            ],
            size=14,
            align="justify",
            dir="rtl",
        ),
        B("heading", [R("מקורות", bold=True)], level=2, size=17, align="right", dir="rtl"),
        B("list_item", [R("ספר בראשית")], size=14, marker="א.", dir="rtl"),
        B("list_item", [R("מסכת ברכות")], size=14, marker="ב.", dir="rtl"),
        B(
            "quote",
            [R("בְּרֵאשִׁית בָּרָא אֱלֹהִים אֵת הַשָּׁמַיִם וְאֵת הָאָרֶץ")],
            size=16,
            align="center",
            dir="rtl",
        ),
        B(
            "paragraph",
            [R("The Hebrew word "), R("שלום", bold=True), R(" means peace, and it often appears inside English sentences.")],
            size=12,
            align="left",
            dir="ltr",
        ),
        B(
            "paragraph",
            [R("דאָס איז אַ ייִדיש זאַץ פֿון אַ בוך.")],
            size=14,
            align="right",
            dir="rtl",
        ),
        B("paragraph", [R("הערה חשובה בצבע אדום.", color=RED)], size=14, align="right", dir="rtl"),
    ]
]

# ---------------------------------------------------------------- table + figure (1 page)
TABLE = [
    [
        B("heading", [R("Quarterly Results", bold=True)], level=1, size=22, align="left", font="sans-serif"),
        B(
            "paragraph",
            [R("The table below summarises sales by region. Figures are in thousands of dollars.")],
            size=12,
            align="left",
            font="sans-serif",
        ),
        B(
            "table",
            [],
            size=11,
            font="sans-serif",
            rows=[
                [{"t": "Region", "h": True}, {"t": "Q1", "h": True}, {"t": "Q2", "h": True}, {"t": "Total", "h": True}],
                [{"t": "North"}, {"t": "120"}, {"t": "135"}, {"t": "255"}],
                [{"t": "South"}, {"t": "98"}, {"t": "110"}, {"t": "208"}],
                [{"t": "Combined (both regions)", "colspan": 3}, {"t": "463"}],
            ],
        ),
        B("caption", [R("Table 1. Sales by region.", italic=True)], size=10, align="center", font="sans-serif"),
        B("figure", [], figure="Bar chart comparing the two regions", width_frac=0.5),
        B("caption", [R("Figure 1. North sold more in both quarters.", italic=True)], size=10, align="center", font="sans-serif"),
        B(
            "paragraph",
            [R("Growth was steady. "), R("Note:", bold=True), R(" the combined total includes both regions.")],
            size=12,
            align="left",
            font="sans-serif",
        ),
    ]
]

# ---------------------------------------------------------------- sefer layout with regions (1 page)
SEFER = [
    [
        B("heading", [R("מסכת ברכות", bold=True)], level=1, size=26, align="center", dir="rtl", region="main"),
        B(
            "paragraph",
            [R("מאימתי קורין את שמע בערבין. משעה שהכהנים נכנסים לאכול בתרומתן עד סוף האשמורה הראשונה, דברי רבי אליעזר.")],
            size=16,
            align="justify",
            dir="rtl",
            region="main",
            box="main",
        ),
        B(
            "paragraph",
            [R("מאימתי. פירוש לדוגמה בכתב רש״י, המבאר את דברי המשנה בקצרה ובלשון פשוטה.")],
            size=12,
            align="justify",
            dir="rtl",
            region="rashi",
            font="rashi",
            box="rashi",
        ),
    ]
]

SAMPLES = {"english": ENGLISH, "hebrew": HEBREW, "table": TABLE, "sefer": SEFER}
REGIONS = {
    "sefer": [
        {"id": "main", "label": "Main text", "kind": "main", "font_category": "serif"},
        {"id": "rashi", "label": "Rashi", "kind": "commentary", "font_category": "rashi"},
    ]
}

CHART_SVG = """<svg xmlns='http://www.w3.org/2000/svg' width='300' height='180' viewBox='0 0 300 180'>
<rect x='0' y='0' width='300' height='180' fill='#f4f6f8' stroke='#333' stroke-width='2'/>
<rect x='40' y='60' width='40' height='100' fill='#1F3A5F'/><rect x='90' y='80' width='40' height='80' fill='#7FA7D9'/>
<rect x='170' y='45' width='40' height='115' fill='#1F3A5F'/><rect x='220' y='70' width='40' height='90' fill='#7FA7D9'/>
<line x1='25' y1='160' x2='285' y2='160' stroke='#333' stroke-width='2'/></svg>"""

FONT_STACK = {
    "serif": "'Liberation Serif', 'Times New Roman', serif",
    "sans-serif": "'Liberation Sans', Arial, sans-serif",
    "monospace": "'Liberation Mono', monospace",
    "rashi": "'Noto Rashi Hebrew'",
}
HEBREW_STACK = {
    "serif": "'Frank Ruehl CLM', 'David CLM', serif",
    "sans-serif": "'Heebo', 'Liberation Sans', sans-serif",
    "rashi": "'Noto Rashi Hebrew'",
}


def run_html(run: dict) -> str:
    text = html.escape(run["text"])
    style = []
    if run.get("color"):
        style.append(f"color:{run['color']}")
    if run.get("bold"):
        style.append("font-weight:bold")
    if run.get("italic"):
        style.append("font-style:italic")
    deco = []
    if run.get("underline"):
        deco.append("underline")
    if run.get("strike"):
        deco.append("line-through")
    if deco:
        style.append("text-decoration:" + " ".join(deco))
    if run.get("superscript"):
        text = f"<sup>{text}</sup>"
    if run.get("subscript"):
        text = f"<sub>{text}</sub>"
    if not style:
        return text
    st = ";".join(style)
    return f'<span style="{st}">{text}</span>'


def block_html(i: int, b: dict) -> str:
    font = b.get("font", "serif")
    rtl = b.get("dir") == "rtl"
    family = HEBREW_STACK.get(font, FONT_STACK[font]) if rtl else FONT_STACK[font]
    size = b.get("size", 12)
    style = [f"font-family:{family}", f"font-size:{size}pt", f"text-align:{b.get('align', 'right' if rtl else 'left')}"]
    if b.get("indent"):
        style.append(f"margin-left:{b['indent']}pt;margin-right:{b['indent']}pt")
    st = ";".join(style)
    dir_attr = "rtl" if rtl else "ltr"
    t = b["type"]
    inner = "".join(run_html(r) for r in b["runs"])
    attrs = f'data-gt="{i}" dir="{dir_attr}"'
    if t == "heading":
        lvl = b["level"]
        return f'<h{lvl} {attrs} style="{st};margin:14pt 0 8pt">{inner}</h{lvl}>'
    if t == "list_item":
        pad = "padding-right:28pt" if rtl else "padding-left:28pt"
        marker_pos = "right:0" if rtl else "left:0"
        marker = html.escape(b["marker"])
        return (
            f'<div {attrs} style="{st};position:relative;{pad};margin:3pt 0">'
            f'<span style="position:absolute;{marker_pos}">{marker}</span>{inner}</div>'
        )
    if t == "table":
        rows = []
        for row in b["rows"]:
            cells = []
            for c in row:
                tag = "th" if c.get("h") else "td"
                span = f' colspan="{c["colspan"]}"' if c.get("colspan") else ""
                cells.append(f"<{tag}{span}>{html.escape(c['t'])}</{tag}>")
            rows.append("<tr>" + "".join(cells) + "</tr>")
        return f'<table {attrs} style="{st};border-collapse:collapse;margin:10pt auto;width:80%">' + "".join(rows) + "</table>"
    if t == "figure":
        return f'<div {attrs} style="text-align:center;margin:12pt auto;width:50%">{CHART_SVG}</div>'
    if t in ("header", "footer"):
        pos = "top:0.45in" if t == "header" else "bottom:0.45in"
        return f'<div {attrs} style="{st};position:absolute;left:1in;right:1in;{pos};color:#444">{inner}</div>'
    if t == "footnote":
        return (
            f'<div {attrs} style="{st};position:absolute;left:1in;right:1in;bottom:0.95in;'
            f'border-top:1px solid #888;padding-top:4pt">{inner}</div>'
        )
    return f'<p {attrs} style="{st};margin:6pt 0;line-height:1.35">{inner}</p>'


def page_html(blocks: list[dict], name: str) -> str:
    font_faces = f"""
    @font-face {{ font-family: 'Noto Rashi Hebrew'; src: url('file://{FONTS}/NotoRashiHebrew-Variable.ttf'); }}
    @font-face {{ font-family: 'Heebo'; src: url('file://{FONTS}/Heebo-Variable.ttf'); }}"""
    css = f"""
    {font_faces}
    html, body {{ margin:0; padding:0; background:#fff; }}
    .page {{ position:relative; width:{PAGE_W_IN}in; height:{PAGE_H_IN}in; box-sizing:border-box;
             padding:1in 1in 1.1in 1in; color:#111; }}
    th, td {{ border:1.5px solid #222; padding:5pt 8pt; text-align:left; }}
    th {{ font-weight:bold; background:#fff; }}
    sup, sub {{ font-size:65%; }}
    """
    if name == "sefer":
        main = [b for b in blocks if b.get("box") != "rashi"]
        rashi = [b for b in blocks if b.get("box") == "rashi"]
        body = (
            "<div style='display:flex;flex-direction:row;gap:0.35in'>"
            + "<div style='flex:2'>" + "".join(block_html(blocks.index(b), b) for b in main) + "</div>"
            + "<div style='flex:1;border-right:1px solid #999;padding-right:0.15in;margin-top:0.9in'>"
            + "".join(block_html(blocks.index(b), b) for b in rashi)
            + "</div></div>"
        )
        # Main text sits on the right (read first), the commentary on the left.
        body = body.replace("flex-direction:row", "flex-direction:row-reverse")
    else:
        body = "".join(block_html(i, b) for i, b in enumerate(blocks))
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{css}</style></head><body><div class='page'>{body}</div></body></html>"


def roughen(png: bytes, seed: int) -> Image.Image:
    """Make a clean render look like a scan: paper tone, a little blur and noise."""
    rng = random.Random(seed)
    img = Image.open(io.BytesIO(png)).convert("RGB")
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    paper = Image.new("RGB", img.size, (247, 245, 238))
    img = Image.blend(img, paper, 0.04)
    noise = Image.effect_noise(img.size, 10).convert("RGB")
    img = Image.blend(img, noise, 0.03)
    del rng
    return img


def to_answer_key(blocks: list[dict], boxes: dict[int, list[float]], regions: list[dict]) -> dict:
    out = []
    for i, b in enumerate(blocks):
        runs = [
            {
                "text": r["text"],
                "bold": bool(r.get("bold")),
                "italic": bool(r.get("italic")),
                "underline": bool(r.get("underline")),
                "strikethrough": bool(r.get("strike")),
                "superscript": bool(r.get("superscript")),
                "subscript": bool(r.get("subscript")),
                "color": r.get("color", ""),
                "uncertain": False,
            }
            for r in b["runs"]
        ]
        if b["type"] == "list_item":
            marker = b["marker"]
        else:
            marker = ""
        rows = []
        if b["type"] == "table":
            for row in b["rows"]:
                rows.append(
                    {
                        "cells": [
                            {
                                "runs": [
                                    {
                                        "text": c["t"],
                                        "bold": bool(c.get("h")),
                                        "italic": False,
                                        "underline": False,
                                        "strikethrough": False,
                                        "superscript": False,
                                        "subscript": False,
                                        "color": "",
                                        "uncertain": False,
                                    }
                                ],
                                "colspan": c.get("colspan", 1),
                                "rowspan": 1,
                                "is_header": bool(c.get("h")),
                            }
                            for c in row
                        ]
                    }
                )
        out.append(
            {
                "type": b["type"] if b["type"] != "footer" or not b["runs"][0]["text"].isdigit() else "page_number",
                "region": b.get("region", ""),
                "heading_level": b.get("level", 0) if b["type"] == "heading" else 0,
                "list_level": b.get("level", 0) if b["type"] == "list_item" else 0,
                "list_marker": marker,
                "alignment": b.get("align", "right" if b.get("dir") == "rtl" else "left"),
                "direction": b.get("dir", "ltr"),
                "indent_level": 1 if b.get("indent") else 0,
                "first_line_indent": False,
                "font_size_pt": b.get("size", 12),
                "font_category": b.get("font", "serif"),
                "bbox_frac": boxes[i],
                "continues_on_next_page": bool(b.get("continues")),
                "continues_from_previous_page": bool(b.get("continued")),
                "runs": runs,
                "table_rows": rows,
                "figure_description": b.get("figure", ""),
            }
        )
    return {"regions": regions, "blocks": out}


def build() -> None:
    scale = DPI / 96.0
    with chromium() as browser:
        ctx = browser.new_context(
            viewport={"width": int(PAGE_W_IN * 96), "height": int(PAGE_H_IN * 96)},
            device_scale_factor=scale,
        )
        page = ctx.new_page()
        for name, pages in SAMPLES.items():
            pdf = pymupdf.open()
            key_pages = []
            for p_i, blocks in enumerate(pages):
                page.set_content(page_html(blocks, name), wait_until="load")
                page.wait_for_timeout(150)
                boxes_px = page.evaluate(
                    """() => Array.from(document.querySelectorAll('[data-gt]')).map(e => {
                        const r = e.getBoundingClientRect();
                        return [Number(e.dataset.gt), r.left, r.top, r.right, r.bottom];
                    })"""
                )
                w, h = PAGE_W_IN * 96, PAGE_H_IN * 96
                boxes = {int(i): [round(x0 / w, 4), round(y0 / h, 4), round(x1 / w, 4), round(y1 / h, 4)] for i, x0, y0, x1, y1 in boxes_px}
                png = page.screenshot(full_page=False)
                img = roughen(png, seed=p_i)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=88, dpi=(DPI, DPI))
                pg = pdf.new_page(width=PAGE_W_IN * 72, height=PAGE_H_IN * 72)
                pg.insert_image(pg.rect, stream=buf.getvalue())
                key_pages.append(to_answer_key(blocks, boxes, REGIONS.get(name, [])))
            pdf.save(HERE / f"{name}.pdf", deflate=True)
            (HERE / f"{name}.answer.json").write_text(
                json.dumps({"pages": key_pages}, ensure_ascii=False, indent=1), encoding="utf-8"
            )
            print(f"wrote {name}.pdf ({len(pages)} page(s))")


if __name__ == "__main__":
    build()
