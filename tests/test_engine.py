"""Stage 1 tests: ingest, readers, normalisation, cache and the pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import pymupdf
import pytest
from conftest import needs_tesseract, runs_with
from fake_claude import FakeClaude, answer_pages

from scantodoc.engine import cost, ingest
from scantodoc.engine.pipeline import ConvertSettings, convert_files
from scantodoc.engine.readers.base import ReaderError
from scantodoc.text import base_letters, detect_direction, split_by_direction, strip_marks

def is_reddish(color):
    if not color:
        return False
    r, g, b = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    return r > 140 and r > g + 50 and r > b + 50


# ---------------------------------------------------------------- text helpers


def test_split_by_direction_keeps_logical_order():
    parts = split_by_direction("המילה Rashi היא שם", base="rtl")
    assert "".join(t for t, _ in parts) == "המילה Rashi היא שם"
    assert [d for _, d in parts] == ["rtl", "ltr", "rtl"]
    assert parts[1][0] == "Rashi"


def test_strip_marks_removes_nikud_only():
    assert strip_marks("בְּרֵאשִׁית") == "בראשית"
    assert detect_direction("שלום עולם world") == "rtl"
    assert detect_direction("hello שלום world") == "ltr"


# ---------------------------------------------------------------- ingest


def test_render_scanned_pdf_at_300_dpi(tmp_path, sample):
    pages = ingest.list_pages([sample("english")])
    assert len(pages) == 2
    out = ingest.render(pages[0], tmp_path / "p1.jpg")
    assert (out.width_px, out.height_px, out.dpi) == (2550, 3300, 300)
    assert out.text_layer is None  # an image-only scan


def test_text_layer_is_extracted_in_reading_order(tmp_path):
    font = Path(__file__).parents[1] / "src/scantodoc/fonts/FrankRuhlLibre-Variable.ttf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Chapter One heading text for the test", fontsize=20, fontname="hebo")
    page.insert_font(fontname="frank", fontfile=str(font))
    html = "<p dir='rtl' style='font-family:frank;font-size:16pt'>שלום עולם, זהו מבחן של שכבת טקסט</p>"
    page.insert_htmlbox(pymupdf.Rect(72, 150, 540, 300), html, css=f"@font-face {{font-family: frank; src: url({font.name});}}", archive=pymupdf.Archive(str(font.parent)))
    path = tmp_path / "born-digital.pdf"
    doc.save(path)
    src = ingest.list_pages([path])[0]
    out = ingest.render(src, tmp_path / "p.jpg")
    assert out.text_layer is not None
    words = [w["text"] for w in out.text_layer["words"]]
    assert "Chapter" in words
    assert any(w["bold"] for w in out.text_layer["words"] if w["text"] == "Chapter")
    joined = " ".join(words)
    assert "שלום" in joined and "עולם," in joined  # stored and extracted in logical order


def test_page_ranges():
    assert ingest.parse_page_range("1-3,7", 10) == [0, 1, 2, 6]
    assert ingest.parse_page_range("8-", 10) == [7, 8, 9]
    assert ingest.parse_page_range(None, 3) == [0, 1, 2]


# ---------------------------------------------------------------- local reader (needs Tesseract)


@needs_tesseract
def test_local_reader_english(sample):
    _, doc = convert_files([sample("english")], "en", ConvertSettings(reader="local"))
    p1 = doc.pages[0]
    heads = [b for b in p1.blocks if b.type == "heading"]
    assert heads[0].text == "A Short History of Printing" and heads[0].level == 1
    assert {b.text for b in heads[1:]} >= {"Early Presses", "Why It Mattered"}
    assert all(b.level == 2 for b in heads[1:])
    assert heads[0].font_size == pytest.approx(24, abs=1.5)
    assert heads[1].font_size == pytest.approx(17, abs=1.5)
    assert doc.detected["body"].font_size == pytest.approx(12, abs=1)
    assert heads[0].align == "center"
    # Formatting read from the pixels
    assert [r.text.strip() for r in runs_with(p1.blocks, lambda r: r.bold and r.text.strip() == "single")]
    assert any("hundreds of times" in r.text for r in runs_with(p1.blocks, lambda r: r.italic))
    assert any("consistent" in r.text for r in runs_with(p1.blocks, lambda r: r.underline))
    red = runs_with(p1.blocks, lambda r: is_reddish(r.color) and "soot" in r.text)
    assert red, "the red sentence should keep a red colour"
    assert any(r.color == heads[0].runs[0].color for r in heads[1].runs)  # same navy, snapped
    # Lists, running header, page carry-over
    items = [b for b in p1.blocks if b.type == "list_item"]
    assert [b.text for b in items][:1] == ["Gutenberg Bible, about 1455"] and len(items) == 3
    assert p1.blocks[0].type == "header"
    assert p1.blocks[-1].continues and doc.pages[1].blocks[1].continued
    assert any(b.type == "footnote" for b in doc.pages[1].blocks)


@needs_tesseract
def test_local_reader_hebrew(sample):
    _, doc = convert_files([sample("hebrew")], "he", ConvertSettings(reader="local"))
    blocks = doc.pages[0].blocks
    assert blocks[0].type == "heading" and blocks[0].direction == "rtl" and blocks[0].align == "center"
    assert base_letters(blocks[0].text) == "פרק ראשון: הקדמה"
    para = blocks[1]
    assert para.direction == "rtl"
    assert para.text.startswith("זהו דף לדוגמה")  # logical order, never reversed
    assert "Rashi" in para.text and "Rambam" in para.text
    assert any(r.bold and r.text.strip() == "חשובה" for r in para.runs)
    items = [b for b in blocks if b.type == "list_item"]
    assert [b.list_marker for b in items] == ["א.", "ב."]
    english = next(b for b in blocks if b.text.startswith("The Hebrew word"))
    assert english.direction == "ltr" and "שלום" in english.text
    red = blocks[-1]
    assert red.direction == "rtl" and is_reddish(red.runs[0].color)
    assert doc.main_direction == "rtl"


@needs_tesseract
def test_local_reader_table_and_figure(sample):
    _, doc = convert_files([sample("table")], "tb", ConvertSettings(reader="local"))
    blocks = doc.pages[0].blocks
    table = next(b for b in blocks if b.type == "table")
    rows = [[base_letters("".join(r.text for r in c.runs)) for c in row] for row in table.table.rows]
    assert rows[1] == ["North", "120", "135", "255"]
    assert rows[2] == ["South", "98", "110", "208"]
    assert rows[3][0] == "Combined (both regions)" and table.table.rows[3][0].colspan == 3
    assert table.table.rows[0][0].header
    fig = next(b for b in blocks if b.type == "figure")
    assert fig.figure.image and fig.figure.image.startswith("figures/")
    captions = [b.text for b in blocks if b.type == "caption"]
    assert captions == ["Table 1. Sales by region.", "Figure 1. North sold more in both quarters."]


@needs_tesseract
def test_local_reader_finds_commentary_region(sample):
    _, doc = convert_files([sample("sefer")], "sefer", ConvertSettings(reader="local"))
    page = doc.pages[0]
    assert {r.id for r in page.regions} == {"main", "commentary1"}
    main = [b for b in page.blocks if b.region == "main"]
    comm = [b for b in page.blocks if b.region == "commentary1"]
    assert main[0].type == "heading" and base_letters(main[0].text) == "מסכת ברכות"
    assert comm and all(b.direction == "rtl" for b in comm)


# ---------------------------------------------------------------- Claude reader (stand-in client)


def test_claude_reader_round_trip(sample):
    fake = FakeClaude(answer_pages("hebrew"))
    _, doc = convert_files([sample("hebrew")], "he", ConvertSettings(reader="claude"), claude_client=fake)
    call = fake.calls[0]
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert call["model"] == "claude-haiku-5-5"
    img = call["messages"][0]["content"][0]
    assert img["type"] == "image" and img["source"]["media_type"] == "image/jpeg"
    blocks = doc.pages[0].blocks
    assert blocks[0].type == "heading" and blocks[0].level == 1 and blocks[0].direction == "rtl"
    quote = next(b for b in blocks if b.type == "quote")
    assert quote.text == "בְּרֵאשִׁית בָּרָא אֱלֹהִים אֵת הַשָּׁמַיִם וְאֵת הָאָרֶץ"  # nikud intact
    assert doc.pages[0].usage.calls == 1 and doc.usage.cost_usd > 0


def test_claude_reader_retries_once_on_broken_json(sample):
    fake = FakeClaude(answer_pages("table"), bad_first=1)
    _, doc = convert_files([sample("table")], "tb", ConvertSettings(reader="claude"), claude_client=fake)
    assert len(fake.calls) == 2
    assert fake.calls[1]["messages"][-1]["role"] == "user"
    table = next(b for b in doc.pages[0].blocks if b.type == "table")
    assert table.table.rows[3][0].colspan == 3
    assert doc.pages[0].usage.calls == 2


def test_claude_reader_gives_up_after_second_bad_reply(sample, monkeypatch):
    monkeypatch.setattr("scantodoc.engine.tesseract.find_tesseract", lambda: None)
    fake = FakeClaude(answer_pages("table"), bad_first=2)
    _, doc = convert_files([sample("table")], "tb", ConvertSettings(reader="claude"), claude_client=fake)
    assert doc.pages[0].status == "error" and "not valid" in doc.pages[0].error


def test_claude_refusal_falls_back_to_local_or_errors(sample, monkeypatch):
    monkeypatch.setattr("scantodoc.engine.tesseract.find_tesseract", lambda: None)
    fake = FakeClaude(answer_pages("table"), refuse=True)
    _, doc = convert_files([sample("table")], "tb", ConvertSettings(reader="claude"), claude_client=fake)
    assert doc.pages[0].status == "error" and "declined" in doc.pages[0].error


def test_cache_means_no_second_api_call(sample):
    from scantodoc.engine.pipeline import convert
    from scantodoc.project import Project

    fake = FakeClaude(answer_pages("english"))
    project, _ = convert_files([sample("english")], "en", ConvertSettings(reader="claude"), claude_client=fake)
    assert len(fake.calls) == 2
    # Throw the document away (as after a crash) and convert again: the cache answers.
    project.document_path.unlink()
    doc = convert(Project.open(project.root), ConvertSettings(reader="claude"), claude_client=fake)
    assert len(fake.calls) == 2
    assert doc.pages[0].blocks[1].text == "A Short History of Printing"


def test_claude_regions_and_rashi(sample):
    fake = FakeClaude(answer_pages("sefer"))
    _, doc = convert_files([sample("sefer")], "sefer", ConvertSettings(reader="claude"), claude_client=fake)
    page = doc.pages[0]
    assert [r.label for r in page.regions] == ["Main text", "Rashi"]
    rashi = [b for b in page.blocks if b.region == "rashi"]
    assert rashi and rashi[0].font_category == "rashi"


def test_missing_api_key_is_a_clear_error(sample, monkeypatch):
    monkeypatch.setattr("scantodoc.engine.tesseract.find_tesseract", lambda: None)
    _, doc = convert_files([sample("table")], "tb", ConvertSettings(reader="claude"))
    assert doc.pages[0].status == "error" and "API key" in doc.pages[0].error


@needs_tesseract
def test_hybrid_sends_only_weak_pages_to_claude(sample):
    pages = answer_pages("english") + answer_pages("hebrew")
    fake = FakeClaude(pages)
    settings = ConvertSettings(reader="hybrid", hybrid_threshold=90)
    _, doc = convert_files([sample("english"), sample("hebrew")], "mix", settings, claude_client=fake)
    readers = [p.reader for p in doc.pages]
    assert readers[:2] == ["local", "local"]  # clean English pages stay free
    assert readers[2] == "claude"  # the Hebrew page with nikud scores lower
    assert len(fake.calls) == 1


# ---------------------------------------------------------------- cost


def test_cost_estimate_is_sane():
    est = cost.estimate_pages(200, "claude-haiku-5-5")
    assert 0.05 < est["typical"] < 2.0
    opus = cost.estimate_pages(200, "claude-opus-5-5")
    assert opus["typical"] > 20 * est["typical"]
    w, h = cost.send_size(2550, 3300, "claude-haiku-5-5")
    assert max(w, h) <= 2576 and w * h <= 3_750_000


def test_project_files_are_json(sample):
    fake = FakeClaude(answer_pages("table"))
    project, _ = convert_files([sample("table")], "tb", ConvertSettings(reader="claude"), claude_client=fake)
    data = json.loads(project.document_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1 and data["pages"][0]["status"] == "done"
    assert (project.root / "sources" / "table.pdf").exists()


def test_reader_error_type():
    assert issubclass(ReaderError, RuntimeError)
