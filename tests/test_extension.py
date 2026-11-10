"""The browser extension, loaded into a real Chromium and talking to a real (local-only) ScanToDoc."""

from __future__ import annotations

import functools
import http.server
import socket
import tempfile
import threading
import time
from pathlib import Path

import pytest
from docx import Document as Docx

from conftest import SAMPLES, needs_tesseract
from scantodoc import browser
from scantodoc.web.app import EXTENSION_ID, create_app

EXTENSION = Path(__file__).parent.parent / "browser-extension"
BASE = f"chrome-extension://{EXTENSION_ID}"

pytestmark = [pytest.mark.chromium, needs_tesseract]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def scantodoc_port():
    import uvicorn

    port = free_port()
    server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield port
    server.should_exit = True
    thread.join(5)


@pytest.fixture
def website():
    """A small website on this computer serving the sample files (and one web page)."""
    folder = Path(tempfile.mkdtemp())
    for name in ("english.pdf", "table.pdf"):
        (folder / name).write_bytes((SAMPLES / name).read_bytes())
    (folder / "page.html").write_text("<p>Just a web page</p>")
    (folder / "scan").write_bytes((SAMPLES / "table.pdf").read_bytes())  # no extension, typed by the server
    handler = functools.partial(QuietHandler, directory=str(folder))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, "": "application/pdf"}

    def log_message(self, *args):
        pass


@pytest.fixture
def chrome(tmp_path):
    from playwright.sync_api import sync_playwright

    args = [f"--disable-extensions-except={EXTENSION}", f"--load-extension={EXTENSION}"]
    with sync_playwright() as p:
        context = None
        for kw in [{}, *({"executable_path": path} for path in browser._candidate_paths())]:
            try:
                context = p.chromium.launch_persistent_context(
                    str(tmp_path / "profile"), headless=True, args=args, downloads_path=str(tmp_path / "dl"), **kw
                )
                break
            except Exception:  # noqa: BLE001 - try the next browser
                continue
        if context is None:
            pytest.skip("no Chromium that can load extensions")
        for _ in range(100):
            if context.service_workers:
                break
            time.sleep(0.1)
        yield context
        context.close()


def open_page(context, name: str, port: int):
    page = context.new_page()
    page.goto(f"{BASE}/{name}")
    page.evaluate("port => chrome.storage.sync.set({settings: {port}})", port)
    page.reload()
    return page


def wait_for_job(page, steps=("done", "error", "needs-permission"), timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        jobs = page.evaluate("chrome.storage.local.get('jobs').then(r => r.jobs || [])")
        if jobs and jobs[0]["step"] in steps:
            return jobs[0]
        time.sleep(0.3)
    raise AssertionError(f"job did not finish: {jobs}")


def saved_file(page, job, mime: str = "") -> Path:
    """The downloaded file. (Under test, the browser saves downloads under random names.)"""
    item = page.evaluate("id => chrome.downloads.search({id}).then(r => r[0])", job["downloadId"])
    assert item["state"] == "complete"
    assert mime in item["mime"]
    return Path(item["filename"])


def test_popup_shows_scantodoc_and_remembers_choices(chrome, scantodoc_port):
    page = open_page(chrome, "popup.html", scantodoc_port)
    page.wait_for_selector("[data-testid=connected]")
    assert "English" in page.inner_text("[data-testid=connected]")
    assert page.locator("[data-testid=format] option").count() >= 4
    assert page.locator("[data-testid=preset] option").count() == 4
    page.select_option("[data-testid=format]", "txt")
    page.reload()
    page.wait_for_selector("[data-testid=connected]")
    assert page.input_value("[data-testid=format]") == "txt"
    assert "Right-click a PDF link" in page.inner_text("#jobs")


def test_popup_explains_when_scantodoc_is_not_running(chrome):
    page = open_page(chrome, "popup.html", free_port())
    page.wait_for_selector("[data-testid=retry]")
    assert "isn't running" in page.inner_text("#status")
    assert page.locator("[data-testid=convert-files]").is_disabled()


def test_convert_files_from_this_computer(chrome, scantodoc_port):
    page = open_page(chrome, "convert.html", scantodoc_port)
    page.wait_for_selector("[data-testid=connected]")
    page.set_input_files("[data-testid=file-input]", str(SAMPLES / "english.pdf"))
    page.select_option("[data-testid=format]", "docx")
    page.fill("[data-testid=name]", "My scan")
    page.click("[data-testid=convert]")
    page.wait_for_selector("[data-testid=job][data-step=done]", timeout=120000)
    job = wait_for_job(page)
    assert job["name"] == "My scan" and job["total"] == 2 and job["done"] == 2
    path = saved_file(page, job, "wordprocessingml")
    assert "A Short History of Printing" in "\n".join(p.text for p in Docx(path).paragraphs)
    assert "Saved" in page.inner_text("[data-testid=job-text]")


def test_convert_a_pdf_linked_from_a_web_page(chrome, scantodoc_port, website):
    page = open_page(chrome, "popup.html", scantodoc_port)
    page.wait_for_selector("[data-testid=connected]")
    page.select_option("[data-testid=format]", "txt")
    # What the right-click menu does: hand the link to the background worker.
    page.evaluate("url => chrome.runtime.sendMessage({type: 'convertUrl', url})", f"{website}/scan")
    job = wait_for_job(page)
    assert job["step"] == "done", job
    assert job["name"] == "scan"
    text = saved_file(page, job, "text/plain").read_text(encoding="utf-8")
    assert "Quarterly Results" in text
    page.wait_for_selector("[data-testid=job][data-step=done]")

    page.evaluate("url => chrome.runtime.sendMessage({type: 'convertUrl', url})", f"{website}/page.html")
    job = wait_for_job(page)
    assert job["step"] == "error" and "web page, not a PDF" in job["error"]


def test_asks_once_before_downloading_from_other_websites(chrome, scantodoc_port):
    page = open_page(chrome, "popup.html", scantodoc_port)
    page.wait_for_selector("[data-testid=connected]")
    with chrome.expect_page() as opened:
        page.evaluate("chrome.runtime.sendMessage({type: 'convertUrl', url: 'https://scans.example.invalid/book.pdf'})")
    allow = opened.value
    allow.wait_for_selector("[data-testid=allow-card]")
    assert "Allow ScanToDoc to download files from websites" in allow.inner_text("[data-testid=allow-card]")
    job = wait_for_job(page)
    assert job["step"] == "needs-permission" and job["name"] == "book.pdf"
