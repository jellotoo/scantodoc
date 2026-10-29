"""Claude reading the pages itself in a chat: prepare -> page files -> assemble."""

from __future__ import annotations

import json

from click.testing import CliRunner
from docx import Document as Docx

from conftest import needs_tesseract
from fake_claude import answer_pages
from scantodoc.cli import main
from scantodoc.engine import handoff
from scantodoc.project import Project


def prepare(sample, name: str):
    result = CliRunner().invoke(main, ["prepare", str(sample(name)), "--json"])
    assert result.exit_code == 0, result.output
    info = json.loads(result.output)
    return Project.open(info["project"]), info["pages"]


def test_prepare_lists_images_and_rules(sample):
    project, pages = prepare(sample, "english")
    assert [p["page"] for p in pages] == [1, 2]
    for p in pages:
        assert p["image"].endswith(".jpg") and not p["done"]
        assert 8 < p["width_in"] < 9
    rules = (project.root / "agent" / "reading-rules.md").read_text(encoding="utf-8")
    assert "logical order" in rules
    assert json.loads((project.root / "agent" / "schema.json").read_text())["required"] == ["regions", "blocks"]


def test_full_answers_build_the_same_document(sample, tmp_path):
    project, pages = prepare(sample, "table")
    for p, answer in zip(pages, answer_pages("table")):
        with open(p["answer"], "w", encoding="utf-8") as f:
            json.dump(answer, f, ensure_ascii=False)
    out = tmp_path / "out"
    result = CliRunner().invoke(main, ["assemble", str(project.root), "-f", "docx,md", "-o", str(out)])
    assert result.exit_code == 0, result.output
    doc = project.load_document()
    assert all(p.reader == "agent" and p.status == "done" for p in doc.pages)
    tables = [b for _, b in doc.iter_blocks() if b.type == "table"]
    assert tables and any(c.colspan > 1 for row in tables[0].table.rows for c in row)
    assert any((project.root / "figures").iterdir())
    assert (out / f"{project.name}.docx").exists()


def test_short_hand_written_pages(sample, tmp_path):
    project, pages = prepare(sample, "english")
    short = [
        {"blocks": [
            {"type": "heading", "text": "פרק ראשון: הקדמה", "alignment": "center"},
            {"type": "paragraph", "runs": ["זה ", {"text": "מודגש", "bold": True}, " ו-Rambam."], "continues_on_next_page": True},
        ]},
        [
            {"type": "paragraph", "text": "המשך הפסקה.", "continues_from_previous_page": True},
            {"type": "table", "table_rows": [["א", "ב"], {"cells": [{"text": "ג", "colspan": 2}]}]},
            {"type": "list_item", "text": "Item one", "list_marker": "1."},
        ],
    ]
    for p, page in zip(pages, short):
        with open(p["answer"], "w", encoding="utf-8") as f:
            json.dump(page, f, ensure_ascii=False)
    doc, problems = handoff.assemble(project)
    assert problems == []
    blocks = [b for _, b in doc.iter_blocks()]
    assert blocks[0].type == "heading" and blocks[0].level == 1 and blocks[0].direction == "rtl"
    assert blocks[0].align == "center"
    para = blocks[1]
    assert para.direction == "rtl" and para.align == "right" and para.continues
    assert any(r.bold for r in para.runs)
    out = tmp_path / "short.docx"
    from scantodoc.export import export

    export(doc, project.load_style(), "docx", out, project.root)
    texts = [p.text for p in Docx(out).paragraphs]
    assert any("Rambam" in t and "המשך הפסקה" in t for t in texts)  # joined across the page break
    table = next(b for b in blocks if b.type == "table")
    assert table.table.rows[1][0].colspan == 2
    item = next(b for b in blocks if b.type == "list_item")
    assert item.direction == "ltr" and item.list_marker == "1."


def test_problems_are_reported_and_nothing_is_saved(sample):
    project, pages = prepare(sample, "english")
    with open(pages[0]["answer"], "w", encoding="utf-8") as f:
        json.dump({"blocks": [{"type": "headline", "text": "x"}]}, f)
    result = CliRunner().invoke(main, ["assemble", str(project.root), "--check"])
    assert result.exit_code != 0
    assert "Page 1" in result.output and "blocks.0.type" in result.output
    assert "Page 2" in result.output and "not been written" in result.output
    with open(pages[0]["answer"], "w", encoding="utf-8") as f:
        f.write("{not json")
    doc, problems = handoff.assemble(project)
    assert doc is None and "not valid JSON" in problems[0]
    assert all(p.status != "done" for p in project.load_document().pages)


def test_allow_missing_builds_what_is_there(sample, tmp_path):
    project, pages = prepare(sample, "english")
    with open(pages[0]["answer"], "w", encoding="utf-8") as f:
        json.dump(answer_pages("english")[0], f)
    out = tmp_path / "o"
    result = CliRunner().invoke(main, ["assemble", str(project.root), "--allow-missing", "-f", "docx", "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert "could not be read: 2" in result.output
    text = "\n".join(p.text for p in Docx(next(out.glob("*.docx"))).paragraphs)
    assert "A Short History of Printing" in text


@needs_tesseract
def test_hand_over_only_the_hard_pages_of_a_local_conversion(sample, tmp_path):
    result = CliRunner().invoke(main, ["convert", str(sample("english")), "-f", "txt", "-o", str(tmp_path)])
    assert result.exit_code == 0, result.output
    from scantodoc.project import list_projects

    project = list_projects()[0]
    before = project.load_document().pages[0].blocks
    result = CliRunner().invoke(main, ["prepare", str(project.root), "--pages", "2", "--json"])
    assert result.exit_code == 0, result.output
    listed = json.loads(result.output)["pages"]
    assert [p["page"] for p in listed] == [2]
    with open(listed[0]["answer"], "w", encoding="utf-8") as f:
        json.dump([{"type": "paragraph", "text": "Read again in the chat."}], f)
    doc, problems = handoff.assemble(project)
    assert problems == []
    assert [p.reader for p in doc.pages] == ["local", "agent"]
    assert [b.text for b in doc.pages[0].blocks] == [b.text for b in before]
    assert doc.pages[1].blocks[0].text == "Read again in the chat."
