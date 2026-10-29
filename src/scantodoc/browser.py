"""Find a Chromium-family browser for PDF export.

Order of preference: Playwright's own Chromium, then Microsoft Edge (always
present on Windows), then Google Chrome, then a path from the
SCANTODOC_CHROMIUM environment variable or a few well-known locations.
"""

from __future__ import annotations

import contextlib
import glob
import os
from typing import Iterator


class BrowserUnavailable(RuntimeError):
    pass


def _candidate_paths() -> list[str]:
    paths = []
    env = os.environ.get("SCANTODOC_CHROMIUM")
    if env:
        paths.append(env)
    paths += sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome"), reverse=True)
    paths += [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
    ]
    return [p for p in paths if os.path.exists(p)]


@contextlib.contextmanager
def chromium() -> Iterator[object]:
    """Yield a launched Playwright Browser; raise BrowserUnavailable if none works."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - playwright is a dependency
        raise BrowserUnavailable("The 'playwright' package is not installed.") from exc

    errors = []
    with sync_playwright() as p:
        attempts = [("playwright chromium", {})]
        attempts += [(f"channel {c}", {"channel": c}) for c in ("msedge", "chrome")]
        attempts += [(path, {"executable_path": path}) for path in _candidate_paths()]
        browser = None
        for label, kwargs in attempts:
            try:
                browser = p.chromium.launch(**kwargs)
                break
            except Exception as exc:  # noqa: BLE001 - try the next candidate
                errors.append(f"{label}: {str(exc).splitlines()[0][:160]}")
        if browser is None:
            raise BrowserUnavailable(
                "No Chromium-based browser was found for PDF export. Run "
                "'python -m playwright install chromium' once, or install Google Chrome "
                "or Microsoft Edge.\n" + "\n".join(errors)
            )
        try:
            yield browser
        finally:
            browser.close()


def available() -> bool:
    try:
        with chromium():
            return True
    except BrowserUnavailable:
        return False
