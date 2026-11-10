"""The web app's API: projects, converting, live preview, editing, exports, presets, the API key."""

from __future__ import annotations

import io
import json
import time
import zipfile

import pytest
from docx import Document as Docx
from fastapi.testclient import TestClient

from conftest import needs_tesseract
from fake_claude import FakeClaude, answer_pages
from scantodoc import config
from scantodoc.web.app import create_app

def make_client(**kw):
    return TestClient(create_app(**kw), base_url="http://127.0.0.1:8765")


SECRET = "sk-ant-api03-THIS-IS-A-TEST-KEY-0123456789abcdef"


def upload(client, sample, name=None):
    with open(sample, "rb") as fh:
        r = client.post("/api/projects", files=[("files", (sample.name, fh, "application/pdf"))], data={"name": name or sample.stem})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def convert(client, pid, **body):
    r = client.post(f"/api/projects/{pid}/convert", json=body)
    assert r.status_code == 200, r.text
    events = []
    with client.stream("GET", f"/api/projects/{pid}/events") as s:
        for line in s.iter_lines():
            if line.startswith("data: "):
                ev = json.loads(line[6:])
                if "type" in ev:  # skip the closing "end" event
                    events.append(ev)
    deadline = time.time() + 60
    while client.get(f"/api/projects/{pid}").json()["job"]["status"] == "running" and time.time() < deadline:
        time.sleep(0.1)
    return events


def test_api_key_never_reaches_the_browser(monkeypatch):
    client = make_client()
    assert client.get("/api/config").json()["has_api_key"] is False
    r = client.post("/api/key", json={"key": SECRET})
    assert r.json() == {"has_api_key": True}
    assert SECRET in (config.home() / ".env").read_text()
    for url in ("/api/config", "/api/projects", "/api/presets"):
        assert SECRET not in client.get(url).text
    assert client.get("/api/config").json()["has_api_key"] is True
    assert client.delete("/api/key").json() == {"has_api_key": False}
    assert client.post("/api/key", json={"key": "nonsense"}).status_code == 422
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    text = client.get("/api/config").text
    assert SECRET not in text and json.loads(text)["has_api_key"] is True


def test_upload_rejects_non_documents_and_bad_paths(sample):
    client = make_client()
    r = client.post("/api/projects", files=[("files", ("notes.txt", b"hello", "text/plain"))])
    assert r.status_code == 422
    pid = upload(client, sample("english"))
    for url in (
        "/api/projects/..%2F..%2Fetc",
        "/api/projects/../home",
        f"/api/projects/{pid}/pages/..%2Fproject.json",
        f"/api/projects/{pid}/figures/..%2F..%2Fstyle.json",
        "/api/presets/..%2F..%2Fsecret",
    ):
        assert client.get(url).status_code == 404, url
    assert client.post(f"/api/projects/{pid}/convert", json={"reader": "claude"}).status_code == 422  # no key


def test_estimate_before_converting(sample):
    client = make_client()
    pid = upload(client, sample("english"))
    local = client.post(f"/api/projects/{pid}/estimate", json={"reader": "local"}).json()
    assert local["pages"] == 2 and local["typical"] == 0
    claude = client.post(f"/api/projects/{pid}/estimate", json={"reader": "claude", "pages": "1"}).json()
    assert claude["pages"] == 1 and 0 < claude["low"] <= claude["typical"] <= claude["high"]
    sonnet = client.post(f"/api/projects/{pid}/estimate", json={"reader": "claude", "model": "claude-sonnet-5-5"}).json()
    assert sonnet["typical"] > claude["typical"]


@needs_tesseract
def test_local_conversion_preview_edit_and_exports(sample):
    client = make_client()
    pid = upload(client, sample("english"), "Printing history")
    events = convert(client, pid, reader="local")
    kinds = [e["type"] for e in events]
    assert kinds[0] == "render" and "start" in kinds and kinds[-1] == "done"
    assert sum(k == "page_done" for k in kinds) == 2

    project = client.get(f"/api/projects/{pid}").json()
    assert project["status"] == "done"
    doc = project["document"]
    assert [p["status"] for p in doc["pages"]] == ["done", "done"]

    # The preview is the real HTML exporter's output, per page, with block ids.
    pv = client.post(f"/api/projects/{pid}/preview", json={}).json()
    assert set(pv["pages"]) == {"0", "1"}
    assert "<h1" in pv["pages"]["0"] and "A Short History of Printing" in pv["pages"]["0"]
    assert 'data-dropped="1"' in pv["pages"]["0"]  # the running head is shown, marked as left out
    # Restyling never re-reads: a different font is just a different preview.
    pv2 = client.post(f"/api/projects/{pid}/preview", json={"fonts": {"body": {"latin": "Georgia"}}}).json()
    assert "Georgia" in pv2["css"] and "Georgia" not in pv["css"]
    assert client.get(f"/api/projects/{pid}").json()["style"]["fonts"]["body"]["latin"] == "Georgia"

    # Editing a block: new text and a new type are saved to the model.
    para = next(b for b in doc["pages"][0]["blocks"] if b["type"] == "paragraph")
    r = client.patch(
        f"/api/projects/{pid}/blocks/{para['id']}",
        json={"type": "heading", "level": 2, "runs": [{"text": "Corrected ", "bold": True}, {"text": "heading"}]},
    )
    assert r.status_code == 200 and r.json()["block"]["user_edited"] is True
    assert client.patch(f"/api/projects/{pid}/blocks/{para['id']}", json={"type": "table"}).status_code == 422
    assert client.patch(f"/api/projects/{pid}/blocks/nope", json={"level": 1}).status_code == 404

    r = client.get(f"/api/projects/{pid}/export/docx")
    assert r.status_code == 200
    assert "Printing%20history.docx" in r.headers["content-disposition"]
    word = Docx(io.BytesIO(r.content))
    edited = [p for p in word.paragraphs if p.text == "Corrected heading"]
    assert edited and edited[0].style.name == "Heading 2"  # (bold comes from the heading style)
    body_font = word.styles["Normal"].element.rPr.rFonts.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}ascii")
    assert body_font == "Georgia"

    for fmt, marker in (("html", b"<!doctype html>"), ("md", b"## Corrected"), ("txt", b"Corrected heading"), ("json", b'"scantodoc"')):
        r = client.get(f"/api/projects/{pid}/export/{fmt}")
        assert r.status_code == 200 and marker in r.content, fmt
    assert client.get(f"/api/projects/{pid}/export/rtf").status_code == 404

    # Delete a block and put it back.
    blk = doc["pages"][1]["blocks"][1]
    assert client.delete(f"/api/projects/{pid}/blocks/{blk['id']}").status_code == 200
    assert blk["id"] not in client.post(f"/api/projects/{pid}/preview", json={}).text
    client.post(f"/api/projects/{pid}/blocks/{blk['id']}/restore", json={"block": blk, "page": 1, "position": 1})
    assert client.get(f"/api/projects/{pid}").json()["document"]["pages"][1]["blocks"][1]["id"] == blk["id"]

    # Page images, with resized copies for thumbnails.
    image = doc["pages"][0]["image"].split("/")[-1]
    full = client.get(f"/api/projects/{pid}/pages/{image}")
    small = client.get(f"/api/projects/{pid}/pages/{image}?w=300")
    assert full.status_code == small.status_code == 200 and len(small.content) < len(full.content)

    listing = client.get("/api/projects").json()
    assert listing[0]["id"] == pid and listing[0]["thumbnail"]
    assert client.delete(f"/api/projects/{pid}").status_code == 200
    assert client.get("/api/projects").json() == []


def test_claude_conversion_rtl_cost_and_figures(sample):
    client = make_client(claude_client=FakeClaude(answer_pages("hebrew")))
    assert client.get("/api/config").json()["has_api_key"] is True
    pid = upload(client, sample("hebrew"))
    events = convert(client, pid, reader="claude")
    done = [e for e in events if e["type"] == "page_done"]
    assert done and done[0]["reader"] == "claude" and done[0]["cost_usd"] > 0
    project = client.get(f"/api/projects/{pid}").json()
    assert project["document"]["main_direction"] == "rtl"
    pv = client.post(f"/api/projects/{pid}/preview", json={}).json()
    assert pv["direction"] == "rtl" and 'dir="rtl"' in pv["pages"]["0"]
    assert "בְּרֵאשִׁית" in pv["pages"]["0"]
    assert "Frank Ruhl Libre" in pv["fonts"] or "David Libre" in pv["fonts"]  # Hebrew web fonts for the preview
    summary = client.get("/api/projects").json()[0]
    assert summary["cost_usd"] > 0

    # A figure from the table sample is served for the preview.
    client2 = make_client(claude_client=FakeClaude(answer_pages("table")))
    pid2 = upload(client2, sample("table"))
    convert(client2, pid2, reader="claude")
    pv = client2.post(f"/api/projects/{pid2}/preview", json={}).json()
    assert "<table" in pv["pages"]["0"] and 'colspan="3"' in pv["pages"]["0"]
    src = pv["pages"]["0"].split('<img src="')[1].split('"')[0]
    assert src.startswith(f"/api/projects/{pid2}/figures/") and client2.get(src).status_code == 200
    r = client2.get(f"/api/projects/{pid2}/export/md")
    assert r.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert any(n.endswith(".md") for n in names) and any("_figures/" in n for n in names)


@needs_tesseract
def test_reread_one_page_with_claude(sample):
    client = make_client(claude_client=FakeClaude(answer_pages("english")))
    pid = upload(client, sample("english"))
    convert(client, pid, reader="local")
    r = client.post(f"/api/projects/{pid}/pages/1/reread", json={"reader": "claude"})
    assert r.status_code == 200
    pages = r.json()["document"]["pages"]
    assert pages[0]["reader"] == "local" and pages[1]["reader"] == "claude"
    assert client.post(f"/api/projects/{pid}/pages/9/reread", json={"reader": "claude"}).status_code == 404


def test_presets_crud():
    client = make_client()
    builtin = client.get("/api/presets").json()
    assert {p["key"] for p in builtin} >= {"keep-original", "classic-sefer", "academic", "clean-modern"}
    sefer = client.get("/api/presets/classic-sefer").json()
    assert sefer["fonts"]["body"]["hebrew"]
    style = {"fonts": {"body": {"latin": "Cambria"}}, "spacing": {"line_spacing": 1.5}}
    saved = client.post("/api/presets", json={"name": "My Book", "description": "Mine", "style": style}).json()
    mine = next(p for p in saved if p["key"] == "my-book")
    assert mine["builtin"] is False
    loaded = client.get("/api/presets/my-book").json()
    assert loaded["fonts"]["body"]["latin"] == "Cambria" and loaded["spacing"]["line_spacing"] == 1.5
    assert client.post("/api/presets", json={"name": "Classic sefer", "style": {}}).status_code == 409
    assert client.post("/api/presets", json={"name": "Bad", "style": {"colors": {"link": "nope"}}}).status_code == 422
    assert client.delete("/api/presets/classic-sefer").status_code == 404
    assert client.delete("/api/presets/my-book").status_code == 200
    assert client.get("/api/presets/my-book").status_code == 404


def test_serves_the_app_and_fonts():
    client = make_client()
    r = client.get("/")
    assert r.status_code == 200 and "ScanToDoc" in r.text
    assert client.get("/p/whatever").status_code == 200  # the single-page app handles its own routes
    assert client.get("/fonts/Alef-Regular.ttf").status_code == 200
    assert client.get("/api/nothing").status_code == 404
    fonts = client.get("/api/fonts").json()
    assert any(f["name"] == "Noto Rashi Hebrew" and f["bundled"] for f in fonts["fonts"])


@pytest.mark.parametrize("pages", ["2", "1-1"])
def test_page_ranges(sample, pages):
    client = make_client(claude_client=FakeClaude(answer_pages("english")))
    pid = upload(client, sample("english"))
    convert(client, pid, reader="claude", pages=pages)
    assert len(client.get(f"/api/projects/{pid}").json()["document"]["pages"]) == 1


def test_other_websites_are_turned_away():
    client = TestClient(create_app(), base_url="http://evil.example:8765")  # DNS rebinding
    assert client.get("/api/projects").status_code == 403
    local = make_client()
    r = local.post("/api/key", json={"key": SECRET}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and not config.has_api_key()
    assert local.post("/api/key", json={"key": SECRET}, headers={"Origin": "http://127.0.0.1:8765"}).status_code == 200
    assert TestClient(create_app(), base_url="http://[::1]:8765").get("/api/config").status_code == 200
    assert TestClient(create_app(local_only=False), base_url="http://192.168.1.5:8765").get("/api/config").status_code == 200


def make_style_default():
    from scantodoc.style.options import StyleOptions

    return json.loads(StyleOptions().model_dump_json())


EXTENSION = {"Origin": "chrome-extension://fhkcgfiapfnbhklppenjbkaabmfhpgkl"}


def test_extension_id_matches_the_manifest_key():
    import base64
    import hashlib
    from pathlib import Path

    from scantodoc.web.app import EXTENSION_ID

    manifest = json.loads((Path(__file__).parent.parent / "browser-extension" / "manifest.json").read_text())
    digest = hashlib.sha256(base64.b64decode(manifest["key"])).hexdigest()[:32]
    assert "".join(chr(ord("a") + int(c, 16)) for c in digest) == EXTENSION_ID
    assert EXTENSION["Origin"].endswith(EXTENSION_ID)


@needs_tesseract
def test_browser_extension_free_conversion(sample):
    client = make_client(claude_client=FakeClaude(answer_pages("english")))
    with open(sample("english"), "rb") as fh:
        r = client.post("/api/projects", files=[("files", ("english.pdf", fh, "application/pdf"))], headers=EXTENSION)
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    assert client.post(f"/api/projects/{pid}/style", json={"preset": "classic-sefer"}, headers=EXTENSION).status_code == 200
    assert client.post(f"/api/projects/{pid}/style", json={"preset": "nope"}, headers=EXTENSION).status_code == 404

    # The free extension can never spend the API key, even when one is set.
    for reader in ("claude", "hybrid"):
        r = client.post(f"/api/projects/{pid}/convert", json={"reader": reader}, headers=EXTENSION)
        assert r.status_code == 403 and "local reader" in r.json()["detail"]
    assert client.get(f"/api/projects/{pid}/progress").json()["status"] == "new"

    r = client.post(f"/api/projects/{pid}/convert", json={"reader": "local"}, headers=EXTENSION)
    assert r.status_code == 200, r.text
    deadline = time.time() + 120
    while (prog := client.get(f"/api/projects/{pid}/progress", headers=EXTENSION).json())["status"] == "converting":
        assert time.time() < deadline
        time.sleep(0.2)
    assert prog == {"id": pid, "name": "english", "status": "done", "total": 2, "done": 2, "failed": 0, "error": ""}
    assert client.get(f"/api/projects/{pid}").json()["document"]["pages"][0]["reader"] in ("local", "textlayer")

    r = client.get(f"/api/projects/{pid}/export/docx", headers=EXTENSION)
    assert r.status_code == 200
    text = "\n".join(p.text for p in Docx(io.BytesIO(r.content)).paragraphs)
    assert "Printing" in text
    assert client.get(f"/api/projects/{pid}").json()["style"] != make_style_default()


def test_browser_extension_cannot_do_anything_else(sample, monkeypatch):
    client = make_client()
    pid = upload(client, sample("english"))
    for method, url, body in [
        ("post", "/api/key", {"key": SECRET}),
        ("delete", "/api/key", None),
        ("post", "/api/presets", {"name": "x", "style": {}}),
        ("delete", f"/api/projects/{pid}", None),
        ("post", f"/api/projects/{pid}/preview", {}),
        ("post", f"/api/projects/{pid}/pages/0/reread", {"reader": "local"}),
    ]:
        kw = {"headers": EXTENSION}
        if body is not None:
            kw["json"] = body
        r = getattr(client, method)(url, **kw)
        assert r.status_code == 403, (url, r.status_code)
        assert r.json()["detail"] == "The browser extension cannot do that."
    assert not config.has_api_key()

    # Some other extension is treated like any other website...
    other = {"Origin": "chrome-extension://abcdefghijklmnopabcdefghijklmnop"}
    assert client.post(f"/api/projects/{pid}/convert", json={"reader": "local"}, headers=other).status_code == 403
    # ...unless the person allows it by its ID.
    monkeypatch.setenv("SCANTODOC_EXTENSION_IDS", "abcdefghijklmnopabcdefghijklmnop")
    assert client.post(f"/api/projects/{pid}/style", json={"preset": "academic"}, headers=other).status_code == 200
