"""The web app in a real browser: upload, convert, live restyle, inline editing, download, themes, phone layout."""

from __future__ import annotations

import socket
import threading
import time

import pytest

from fake_claude import FakeClaude, answer_pages
from scantodoc import browser
from scantodoc.web.app import STATIC_DIR, create_app

pytestmark = [
    pytest.mark.chromium,
    pytest.mark.skipif(not (STATIC_DIR / "index.html").exists(), reason="the web interface is not built"),
]


@pytest.fixture(scope="module")
def chromium_ok():
    if not browser.available():
        pytest.skip("no Chromium-based browser")


@pytest.fixture
def server(chromium_ok):
    import uvicorn

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    app = create_app(claude_client=FakeClaude(answer_pages("english")))
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    t.join(5)


def shadow(page, js):
    return page.evaluate(f"() => {{ const r = document.querySelector('[data-testid=preview-host]').shadowRoot; return {js}; }}")


def test_full_journey(server, sample, tmp_path):
    with browser.chromium() as b:
        page = b.new_page(viewport={"width": 1400, "height": 900}, accept_downloads=True)
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        requests = []
        page.on("request", lambda r: requests.append(r.url))

        page.goto(server)
        page.wait_for_selector("[data-testid=dropzone]")
        page.set_input_files("[data-testid=file-input]", str(sample("english")))

        # Convert with Claude (a stand-in that answers like Claude would).
        page.wait_for_selector("[data-testid=start-convert]")
        page.click("role=radio[name=/^Claude \\(best\\)/]")
        page.wait_for_function("document.querySelector('[data-testid=estimate]').innerText.includes('estimated cost')")
        page.click("[data-testid=start-convert]")
        page.wait_for_selector("[data-testid=cost]", timeout=60000)
        page.wait_for_selector("[data-testid=progress]", state="detached", timeout=60000)
        page.wait_for_function(
            "document.querySelector('[data-testid=preview-host]').shadowRoot.querySelector('h1') !== null", timeout=10000
        )
        assert "A Short History of Printing" in shadow(page, "r.querySelector('h1').textContent")
        assert page.locator("[data-testid=scan-pane] img").count() == 2
        assert "$" in page.inner_text("[data-testid=cost]")

        # Live restyle: the preview changes, nothing is read again.
        converts = sum("/convert" in u for u in requests)
        page.locator("[data-testid=style-panel] input[list=fonts-latin]").first.fill("Georgia")
        page.wait_for_function(
            "getComputedStyle(document.querySelector('[data-testid=preview-host]').shadowRoot.querySelector('p.e-body')).fontFamily.startsWith('Georgia')"
        )
        assert sum("/convert" in u for u in requests) == converts

        # Select a block, change its type, then edit its text in place.
        page.locator("[data-testid=preview-host] h2").first.click()
        page.select_option("[data-testid=block-type]", "heading:3")
        page.wait_for_function("document.querySelector('[data-testid=preview-host]').shadowRoot.querySelectorAll('h3').length >= 1")
        para = page.locator("[data-testid=preview-host] p.e-body").first
        para.dblclick()
        page.wait_for_selector("[data-testid=save-edit]")
        page.keyboard.press("Control+End")
        page.keyboard.type(" Fixed by hand.")
        page.click("[data-testid=save-edit]")
        page.wait_for_function(
            "document.querySelector('[data-testid=preview-host]').shadowRoot.querySelector('p.e-body').textContent.includes('Fixed by hand.')"
        )

        # Download a Word file that contains the correction.
        with page.expect_download() as dl:
            page.click("[data-testid=download-button]")
            page.click("[data-testid=export-docx]")
        path = tmp_path / dl.value.suggested_filename
        dl.value.save_as(path)
        from docx import Document as Docx

        text = "\n".join(p.text for p in Docx(path).paragraphs)
        assert "Fixed by hand." in text and path.suffix == ".docx"

        # Dark mode and the narrow (phone) layout.
        page.click("button[title^='Theme']")
        page.click("button[title^='Theme']")
        assert page.evaluate("document.documentElement.classList.contains('dark')")
        page.set_viewport_size({"width": 390, "height": 844})
        page.click("role=tab[name=Style]")
        assert page.locator("[data-testid=style-panel]").is_visible()
        page.click("role=tab[name=Scan]")
        assert page.locator("[data-testid=scan-pane]").is_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

        # The project is listed on the home page.
        page.goto(server + "/#/")
        page.wait_for_selector("[data-testid=projects] li")
        assert errors == []
