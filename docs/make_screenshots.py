"""Make the README screenshots (docs/screenshots/*.png).

Runs the web app on a private, empty ScanToDoc folder with a stand-in for
Claude (the test suite's FakeClaude), so no API key is used and nothing is
sent anywhere. Run from the scantodoc folder:

    python docs/make_screenshots.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "screenshots"
os.environ["SCANTODOC_HOME"] = tempfile.mkdtemp(prefix="scantodoc-shots-")
os.environ.pop("ANTHROPIC_API_KEY", None)
sys.path.insert(0, str(ROOT / "tests"))

import uvicorn  # noqa: E402
from fake_claude import FakeClaude, answer_pages  # noqa: E402

from scantodoc.browser import chromium  # noqa: E402
from scantodoc.web.app import create_app  # noqa: E402

PORT = 8799
URL = f"http://127.0.0.1:{PORT}"
SAMPLES = ROOT / "tests" / "samples"


class Answers(FakeClaude):
    """Answers like Claude would for whichever sample is being read."""

    def __init__(self):
        self.by_sample = {n: answer_pages(n) for n in ("english", "hebrew", "sefer", "table")}
        self.current = "english"
        super().__init__(self.by_sample["english"])

    def use(self, name: str) -> None:
        self.current = name
        self.pages = self.by_sample[name]


def start_server(client) -> uvicorn.Server:
    server = uvicorn.Server(uvicorn.Config(create_app(claude_client=client), host="127.0.0.1", port=PORT, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            return server
        time.sleep(0.05)
    raise RuntimeError("the web app did not start")


def convert(page, client: Answers, sample: str) -> None:
    client.use(sample)
    page.goto(URL + "/#/")
    page.wait_for_selector("[data-testid=dropzone]")
    page.set_input_files("[data-testid=file-input]", str(SAMPLES / f"{sample}.pdf"))
    page.wait_for_selector("[data-testid=start-convert]")
    page.click("role=radio[name=/^Claude \\(best\\)/]")
    page.wait_for_function("document.querySelector('[data-testid=estimate]').innerText.length > 0")
    page.click("[data-testid=start-convert]")
    wait_until_read(page)


def wait_until_read(page) -> None:
    page.wait_for_selector("[data-testid=cost]", timeout=120000)
    page.wait_for_selector("[data-testid=progress]", state="detached", timeout=120000)
    page.wait_for_function(
        "document.querySelector('[data-testid=preview-host]')?.shadowRoot?.querySelector('h1, h2, p.e-body, table') != null"
    )
    time.sleep(1.2)


def shot(page, name: str) -> None:
    page.screenshot(path=str(OUT / f"{name}.png"))
    print("  saved", name)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    client = Answers()
    server = start_server(client)
    try:
        with chromium() as browser:
            page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
            page.emulate_media(color_scheme="light")

            # 1. The start page, empty.
            page.goto(URL)
            page.wait_for_selector("[data-testid=dropzone]")
            time.sleep(0.5)
            shot(page, "01-start")

            # 2. The convert dialog with its cost estimate.
            client.use("hebrew")
            page.set_input_files("[data-testid=file-input]", str(SAMPLES / "hebrew.pdf"))
            page.wait_for_selector("[data-testid=start-convert]")
            page.click("role=radio[name=/^Claude \\(best\\)/]")
            page.wait_for_function("document.querySelector('[data-testid=estimate]').innerText.includes('estimated')")
            time.sleep(0.4)
            shot(page, "02-convert-dialog")
            page.click("[data-testid=start-convert]")
            wait_until_read(page)

            # 3. Hebrew page: scan and result side by side.
            shot(page, "03-workspace-hebrew")

            # 4. English with a table and a picture, one block selected.
            convert(page, client, "table")
            page.locator("[data-testid=preview-host] table").first.click()
            time.sleep(0.6)
            shot(page, "04-workspace-table")

            # 5. Editing a paragraph in place.
            convert(page, client, "english")
            page.locator("[data-testid=preview-host] p.e-body").first.dblclick()
            page.wait_for_selector("[data-testid=save-edit]")
            page.keyboard.press("Control+End")
            page.keyboard.type(" (corrected)")
            time.sleep(0.4)
            shot(page, "05-editing")
            page.click("[data-testid=save-edit]")
            time.sleep(0.8)

            # 6. Gemara-style page with a Rashi region.
            convert(page, client, "sefer")
            page.select_option("[data-testid=preset-select]", "classic-sefer")
            time.sleep(1.2)
            shot(page, "06-sefer")

            # 7. The projects list (after the "done" message has faded).
            time.sleep(6)
            page.goto(URL + "/#/")
            page.wait_for_selector("[data-testid=projects] li")
            page.mouse.move(5, 5)
            time.sleep(1.0)
            shot(page, "07-projects")

            # 8. Dark mode on a phone-sized window.
            page.evaluate("localStorage.setItem('scantodoc-theme', 'dark')")
            page.click("[data-testid=projects] a >> nth=0")
            page.wait_for_selector("[data-testid=preview-host]")
            page.reload()
            page.wait_for_selector("[data-testid=preview-host]")
            time.sleep(1.5)
            page.set_viewport_size({"width": 390, "height": 844})
            time.sleep(1.0)
            shot(page, "08-phone")
    finally:
        server.should_exit = True


if __name__ == "__main__":
    main()
