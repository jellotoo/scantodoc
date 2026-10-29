"""Settings: where projects live, and how the Claude API key is found.

The API key is read from the ANTHROPIC_API_KEY environment variable, or from
a `.env` file (a plain text file containing a line `ANTHROPIC_API_KEY=...`)
in the current folder or in the ScanToDoc folder in your home directory.
The key is only ever used on this computer; the web app never sends it to
the browser.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

KEY_NAME = "ANTHROPIC_API_KEY"


def home() -> Path:
    """The ScanToDoc folder: projects, presets and settings live here."""
    root = Path(os.environ.get("SCANTODOC_HOME") or (Path.home() / "ScanToDoc"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def projects_dir() -> Path:
    d = home() / "projects"
    d.mkdir(parents=True, exist_ok=True)
    return d


def presets_dir() -> Path:
    d = home() / "presets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _env_files() -> list[Path]:
    return [Path.cwd() / ".env", home() / ".env"]


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        k, v = line.split("=", 1)
        values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def api_key() -> Optional[str]:
    key = os.environ.get(KEY_NAME)
    if key:
        return key.strip()
    for f in _env_files():
        key = _read_env_file(f).get(KEY_NAME)
        if key:
            return key
    return None


def has_api_key() -> bool:
    return bool(api_key())


def save_api_key(key: str) -> Path:
    """Store the key in ~/ScanToDoc/.env (used by the web app's settings box)."""
    path = home() / ".env"
    values = _read_env_file(path)
    values[KEY_NAME] = key.strip()
    path.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def remove_api_key() -> None:
    path = home() / ".env"
    values = _read_env_file(path)
    values.pop(KEY_NAME, None)
    path.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
