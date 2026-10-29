"""Stage 2 tests: the command line."""

from __future__ import annotations

import json

from click.testing import CliRunner
from conftest import needs_tesseract
from docx import Document as open_docx
from docx.oxml.ns import qn

from scantodoc.cli import build_style, main


def run(*args):
    result = CliRunner().invoke(main, list(args), catch_exceptions=False)
    return result


def test_every_command_has_help():
    for cmd in ["convert", "restyle", "batch", "serve", "estimate", "doctor", "projects", "fonts", "preset"]:
        r = run(cmd, "--help")
        assert r.exit_code == 0 and "Usage:" in r.output
    r = run("convert", "--help")
    for opt in ["--preset", "--body-font", "--hebrew-font", "--heading-color", "--scale", "--keep-headers", "--toc", "--reader"]:
        assert opt in r.output


def test_style_flags_map_to_options():
    s = build_style(
        preset="Classic sefer", body_font="Times New Roman", hebrew_font="Frank Ruehl", heading_color="#1F3A5F",
        scale=110, keep_headers=True, margins="0.75", page_size="6x9", element_font=("h1=Georgia",),
        colors=("body=#222222",), toc=True, sets=("extras.toc_title=Inhalt",),
    )
    assert s.fonts.body.latin == "Times New Roman" and s.fonts.body.hebrew == "Frank Ruehl"
    assert s.colors.mode == "custom" and s.colors.custom["h2"] == "#1F3A5F" and s.colors.custom["body"] == "#222222"
    assert s.sizes.mode == "scale" and s.sizes.scale == 110
    assert s.extras.keep_headers_footers and s.extras.toc and s.extras.toc_title == "Inhalt"
    assert s.page.size == "custom" and s.page.width_in == 6 and s.page.margins.left == 0.75
    assert s.fonts.elements["h1"].latin == "Georgia"
    assert s.extras.page_numbers  # from the preset
    exact = build_style(sizes=("body=11,h1=20",))
    assert exact.sizes.mode == "exact" and exact.sizes.exact == {"body": 11.0, "h1": 20.0}


def test_bad_values_are_explained():
    r = CliRunner().invoke(main, ["convert", "x.pdf", "--format", "doc"])
    assert r.exit_code != 0
    r = CliRunner().invoke(main, ["preset", "show", "Nope"])
    assert r.exit_code != 0 and "No preset" in r.output


@needs_tesseract
def test_convert_restyle_batch(tmp_path, sample):
    import shutil

    src = tmp_path / "english.pdf"
    shutil.copy(sample("english"), src)
    r = run("convert", str(src), "-f", "docx,md,json", "--preset", "Classic sefer", "--heading-color", "#1F3A5F", "--scale", "110")
    assert r.exit_code == 0, r.output
    d = open_docx(tmp_path / "english.docx")
    assert str(d.styles["Heading 1"].font.color.rgb) == "1F3A5F"
    assert d.styles["Heading 1"].font.size.pt == 26.5  # 24 detected x 110%
    assert (tmp_path / "english.md").read_text(encoding="utf-8").startswith("# A Short History of Printing")
    # Re-style the JSON bundle: instant, no reading
    r = run("restyle", str(tmp_path / "english.scantodoc.json"), "-f", "docx", "--body-font", "Garamond", "--hebrew-font", "David")
    assert r.exit_code == 0, r.output
    d = open_docx(tmp_path / "english.docx")
    fonts = d.styles["Normal"].element.rPr.find(qn("w:rFonts"))
    assert fonts.get(qn("w:ascii")) == "Garamond" and fonts.get(qn("w:cs")) == "David"
    # Projects list
    r = run("projects", "--json")
    assert json.loads(r.output)[0]["name"] == "english"
    # Batch
    folder = tmp_path / "scans"
    folder.mkdir()
    shutil.copy(sample("table"), folder / "a.pdf")
    shutil.copy(sample("hebrew"), folder / "b.pdf")
    r = run("batch", str(folder), "-f", "txt")
    assert r.exit_code == 0, r.output
    assert (folder / "scantodoc-output" / "a.txt").exists() and (folder / "scantodoc-output" / "b.txt").exists()


def test_claude_reader_without_key_is_refused(tmp_path, sample):
    r = CliRunner().invoke(main, ["convert", str(sample("table")), "--reader", "claude", "-o", str(tmp_path)])
    assert r.exit_code != 0 and "API key" in r.output


def test_preset_save_and_use(tmp_path):
    r = run("preset", "save", "Navy", "--preset", "Clean modern", "--heading-color", "#000080")
    assert r.exit_code == 0
    r = run("preset", "show", "navy")
    assert '"h1": "#000080"' in r.output
