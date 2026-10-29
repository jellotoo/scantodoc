"""Stage 1 tests for styling and export: the generated files are opened and
checked for headings, bold, sizes, colours and right-to-left text."""

from __future__ import annotations

import io
import json
import zipfile

import pymupdf
import pytest
from docx import Document as open_docx
from docx.oxml.ns import qn
from fake_claude import FakeClaude, answer_pages

from scantodoc import browser
from scantodoc.engine.pipeline import ConvertSettings, convert_files
from scantodoc.export import export, load_bundle
from scantodoc.style import presets
from scantodoc.style.options import StyleOptions, set_path


@pytest.fixture
def converted(sample):
    cache = {}

    def get(name):
        if name not in cache:
            fake = FakeClaude(answer_pages(name))
            cache[name] = convert_files([sample(name)], name, ConvertSettings(reader="claude"), claude_client=fake)
        return cache[name]

    return get


def docx_of(converted, name, style=None, tmp_path=None):
    project, doc = converted(name)
    path = export(doc, style or StyleOptions(), "docx", project.root / "exports" / f"{name}.docx", project.root)
    return open_docx(path), path


def paras(d, style_name):
    return [p for p in d.paragraphs if p.style.name == style_name]


def xml(el) -> str:
    return el.xml if hasattr(el, "xml") else el._p.xml


# ---------------------------------------------------------------- Word


def test_docx_uses_real_heading_styles_and_keeps_formatting(converted):
    d, _ = docx_of(converted, "english")
    h1 = paras(d, "Heading 1")
    h2 = paras(d, "Heading 2")
    assert [p.text for p in h1] == ["A Short History of Printing"]
    assert [p.text for p in h2] == ["Early Presses", "Why It Mattered", "Steps in Setting a Page"]
    st = d.styles["Heading 1"]
    assert st.font.size.pt == 24 and st.font.bold
    assert str(st.font.color.rgb) == "1F3A5F"
    assert d.styles["Heading 2"].font.size.pt == 17
    assert d.styles["Normal"].font.size.pt == 12
    runs = [r for p in d.paragraphs for r in p.runs]
    assert any(r.text == "single" and r.bold for r in runs)
    assert any(r.text == "hundreds of times" and r.italic for r in runs)
    assert any(r.text == "consistent" and r.underline for r in runs)
    red = [r for r in runs if "soot" in r.text]
    assert red and str(red[0].font.color.rgb) == "C0392B"
    assert any(r.text == "2" and r.font.superscript for r in runs)
    assert any(r.text == "2" and r.font.subscript for r in runs)
    text = "\n".join(p.text for p in d.paragraphs)
    # running header and printed page numbers are dropped; the split paragraph is joined
    assert "ScanToDoc Sample Report" not in text
    assert "rather than copied forward forever" in text
    assert any(p.text.startswith("•\tGutenberg Bible") for p in d.paragraphs)


def test_docx_right_to_left(converted):
    d, _ = docx_of(converted, "hebrew")
    heading = paras(d, "Heading 1")[0]
    assert heading.text == "פרק ראשון: הקדמה"  # logical order, never reversed
    ppr = heading._p.pPr
    assert ppr.find(qn("w:bidi")) is not None
    assert ppr.find(qn("w:jc")).get(qn("w:val")) == "center"
    body = next(p for p in d.paragraphs if p.text.startswith("זהו דף"))
    assert body._p.pPr.find(qn("w:bidi")) is not None
    assert body._p.pPr.find(qn("w:jc")).get(qn("w:val")) == "both"
    bold = [r for r in body.runs if r.bold]
    assert [r.text for r in bold] == ["חשובה"]
    assert bold[0]._r.rPr.find(qn("w:rtl")) is not None
    assert bold[0]._r.rPr.find(qn("w:bCs")).get(qn("w:val")) == "1"  # Hebrew bold uses the complex-script flag too
    latin = next(r for r in body.runs if r.text == "Rashi")
    assert latin._r.rPr is None or latin._r.rPr.find(qn("w:rtl")) is None
    # A right-aligned Hebrew paragraph is stored as jc=left (start) in Word
    red = next(p for p in d.paragraphs if p.text.startswith("הערה"))
    assert red._p.pPr.find(qn("w:jc")).get(qn("w:val")) == "left"
    nikud = next(p for p in d.paragraphs if p.text.startswith("בְּרֵאשִׁית"))
    assert nikud.text == "בְּרֵאשִׁית בָּרָא אֱלֹהִים אֵת הַשָּׁמַיִם וְאֵת הָאָרֶץ"
    english = next(p for p in d.paragraphs if p.text.startswith("The Hebrew word"))
    assert english._p.pPr.find(qn("w:bidi")) is None
    shalom = next(r for r in english.runs if r.text == "שלום")
    assert shalom.bold and shalom._r.rPr.find(qn("w:rtl")) is not None
    items = [p.text for p in d.paragraphs if p.text.startswith(("א.", "ב."))]
    assert items == ["א.\tספר בראשית", "ב.\tמסכת ברכות"]


def test_docx_table_with_merged_cell(converted):
    d, _ = docx_of(converted, "table")
    t = d.tables[0]
    assert [c.text for c in t.rows[1].cells] == ["North", "120", "135", "255"]
    assert t.rows[3].cells[0].text == "Combined (both regions)"
    assert 'w:gridSpan w:val="3"' in t.rows[3]._tr.xml
    assert all(r.bold for r in t.rows[0].cells[0].paragraphs[0].runs)
    assert d.inline_shapes, "the figure should be in the document"
    assert [p.text for p in paras(d, "Caption")] == ["Table 1. Sales by region.", "Figure 1. North sold more in both quarters."]


def test_classic_sefer_preset_sets_two_fonts_and_black(converted):
    style = presets.load("Classic sefer")
    d, _ = docx_of(converted, "hebrew", style)
    fonts = d.styles["Normal"].element.rPr.find(qn("w:rFonts"))
    assert fonts.get(qn("w:ascii")) == "Times New Roman"
    assert fonts.get(qn("w:cs")) == "Frank Ruehl CLM"
    assert d.styles["Normal"].font.size.pt == 14.5  # 14 pt detected x 105%
    colored = [r for p in d.paragraphs for r in p.runs if r.font.color and r.font.color.rgb not in (None,) and str(r.font.color.rgb) != "000000"]
    assert not colored
    assert str(d.styles["Heading 1"].font.color.rgb) == "000000"
    footer = d.sections[0].footer._element.xml
    assert "PAGE" in footer


def test_custom_options_fonts_colours_sizes(converted):
    s = StyleOptions()
    s = set_path(s, "fonts.body.latin", "Garamond")
    s = set_path(s, "fonts.body.hebrew", "David")
    s = set_path(s, "fonts.elements.h1.latin", "Georgia")
    s = set_path(s, "colors.mode", "custom")
    s = set_path(s, "colors.custom.h1", "#7A1F1F")
    s = set_path(s, "sizes.mode", "exact")
    s = set_path(s, "sizes.exact.body", "11")
    s = set_path(s, "sizes.exact.h1", "30")
    s = set_path(s, "page.size", "a4")
    s = set_path(s, "page.columns", "2")
    s = set_path(s, "extras.toc", "true")
    s = set_path(s, "extras.title_page", "true")
    s = set_path(s, "extras.title", "My Book")
    d, _ = docx_of(converted, "english", s)
    assert d.styles["Heading 1"].font.name == "Georgia"
    assert str(d.styles["Heading 1"].font.color.rgb) == "7A1F1F"
    assert d.styles["Heading 1"].font.size.pt == 30
    assert d.styles["Normal"].font.size.pt == 11 and d.styles["Normal"].font.name == "Garamond"
    sec = d.sections[0]
    assert abs(sec.page_width.inches - 8.27) < 0.01
    assert 'w:num="2"' in sec._sectPr.xml
    body_xml = d.element.body.xml
    assert "TOC \\o" in body_xml
    assert d.paragraphs[6].text == "My Book" or any(p.text == "My Book" and p.style.name == "Title" for p in d.paragraphs)


def test_emphasis_options(converted):
    project, doc = converted("english")
    s = set_path(StyleOptions(), "emphasis.bold", "false")
    d = open_docx(export(doc, s, "docx", project.root / "nobold.docx", project.root))
    assert not any(r.bold for p in d.paragraphs if p.style.name == "Normal" for r in p.runs)
    s = set_path(StyleOptions(), "extras.keep_headers_footers", "true")
    d = open_docx(export(doc, s, "docx", project.root / "heads.docx", project.root))
    assert sum("ScanToDoc Sample Report" in p.text for p in d.paragraphs) == 2


def test_bold_lines_become_headings(converted):
    from scantodoc.model import Run

    project, doc = converted("english")
    doc.pages[1].blocks[3].type = "paragraph"
    doc.pages[1].blocks[3].runs = [Run(text="Pick each letter", bold=True)]
    s = set_path(StyleOptions(), "emphasis.bold_lines_to_headings", "true")
    d = open_docx(export(doc, s, "docx", project.root / "bl.docx", project.root))
    assert any(p.text == "Pick each letter" and p.style.name == "Heading 3" for p in d.paragraphs)


# ---------------------------------------------------------------- other formats


def test_markdown_and_text(converted):
    project, doc = converted("english")
    md = export(doc, StyleOptions(), "md", project.root / "e.md", project.root).read_text(encoding="utf-8")
    assert md.startswith("# A Short History of Printing")
    assert "## Early Presses" in md and "**single**" in md and "*hundreds of times*" in md
    assert "- Gutenberg Bible, about 1455\n- Soncino Hebrew Bible, 1488" in md
    assert "1. Pick each letter from the type case." in md
    assert "rather than copied forward forever" in md
    txt = export(doc, StyleOptions(), "txt", project.root / "e.txt", project.root).read_text(encoding="utf-8")
    assert "A Short History of Printing" in txt and "**" not in txt
    project, doc = converted("table")
    md = export(doc, StyleOptions(), "md", project.root / "t.md", project.root).read_text(encoding="utf-8")
    assert "| North | 120 | 135 | 255 |" in md
    assert "![Bar chart comparing the two regions](t_figures/figure-1.png)" in md
    assert (project.root / "t_figures" / "figure-1.png").exists()


def test_html_has_styles_and_rtl(converted):
    project, doc = converted("hebrew")
    html = export(doc, presets.load("Classic sefer"), "html", project.root / "h.html", project.root).read_text(encoding="utf-8")
    assert '<html lang="he" dir="rtl">' in html
    assert '"Frank Ruehl CLM", "Frank Ruhl Libre"' in html
    assert "@font-face" in html and "Frank Ruhl Libre" in html  # bundled stand-in embedded
    assert '<h1 id="h-' in html and 'dir="rtl"' in html
    assert '<b>חשובה</b>' in html


def test_json_bundle_round_trip_restyles_without_reading(converted):
    project, doc = converted("table")
    path = export(doc, presets.load("Clean modern"), "json", project.root / "t.scantodoc.json", project.root)
    data = json.loads(path.read_text(encoding="utf-8"))
    fig = next(b for b in data["document"]["pages"][0]["blocks"] if b["type"] == "figure")
    assert fig["figure"]["image"].startswith("data:image/png;base64,")
    doc2, style2 = load_bundle(path)
    assert style2.name == "Clean modern"
    out = export(doc2, presets.load("Academic"), "docx", project.root / "again.docx", None)
    d = open_docx(out)
    assert d.inline_shapes and d.tables
    with zipfile.ZipFile(io.BytesIO(out.read_bytes())) as z:
        assert any(n.startswith("word/media/") for n in z.namelist())


def test_presets_list_and_save():
    names = [p["name"] for p in presets.list_presets()]
    assert names[:4] == ["Keep original", "Clean modern", "Classic sefer", "Academic"]
    s = set_path(StyleOptions(), "colors.custom.h1", "#112233")
    presets.save(s, "My navy")
    assert presets.load("my navy").colors.custom["h1"] == "#112233"
    assert any(p["name"] == "My navy" and not p["builtin"] for p in presets.list_presets())
    with pytest.raises(KeyError):
        presets.load("does not exist")


@pytest.mark.skipif(not browser.available(), reason="no Chromium browser for PDF export")
def test_pdf_is_real_text(converted):
    project, doc = converted("hebrew")
    s = set_path(StyleOptions(), "extras.page_numbers", "true")
    path = export(doc, s, "pdf", project.root / "h.pdf", project.root)
    pdf = pymupdf.open(path)
    text = pdf[0].get_text()
    assert "חשובה" in text and "Rashi" in text  # selectable text, Hebrew in reading order
    assert not pdf[0].get_images()  # no picture of the page
    # Fonts are embedded (Chromium stores the bundled variable fonts as Type 3).
    assert len(pdf[0].get_fonts()) >= 2
