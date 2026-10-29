"""PDF export: the styled HTML printed to PDF by a Chromium browser, so the
result is real, selectable, searchable text (not a picture of a page).
If no browser is available, LibreOffice (when installed) converts the
Word export instead."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from ..browser import BrowserUnavailable, chromium
from ..style.resolve import RenderDoc
from .html import render_html


def render_pdf(rdoc: RenderDoc) -> bytes:
    html = render_html(rdoc, font_mode="file", embed_images=False, for_print=True)
    try:
        with chromium() as browser:
            page = browser.new_page()
            with tempfile.TemporaryDirectory() as tmp:
                src = Path(tmp) / "doc.html"
                src.write_text(html, encoding="utf-8")
                page.goto(src.as_uri(), wait_until="load")
                page.evaluate("document.fonts.ready")
                return page.pdf(prefer_css_page_size=True, print_background=True)
    except BrowserUnavailable:
        office = shutil.which("soffice") or shutil.which("libreoffice")
        if not office:
            raise
        return _via_libreoffice(rdoc, office)


def _via_libreoffice(rdoc: RenderDoc, office: str) -> bytes:
    from .docx import render_docx

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "doc.docx"
        src.write_bytes(render_docx(rdoc))
        subprocess.run([office, "--headless", "--convert-to", "pdf", "--outdir", tmp, str(src)], check=True, capture_output=True, timeout=300)
        return (Path(tmp) / "doc.pdf").read_bytes()
