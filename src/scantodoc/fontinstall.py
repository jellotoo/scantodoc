"""Install the bundled free fonts for the current user, so Word can use them."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from .style.fonts import FONTS_DIR


def user_font_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Fonts"
    if sys.platform.startswith("win"):
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Microsoft" / "Windows" / "Fonts"
    return Path.home() / ".local" / "share" / "fonts"


def install_bundled() -> list[str]:
    target = user_font_dir()
    target.mkdir(parents=True, exist_ok=True)
    lines = []
    for src in sorted(FONTS_DIR.glob("*.ttf")):
        dest = target / src.name
        if not dest.exists():
            shutil.copy2(src, dest)
            _register_windows(dest)
            lines.append(f"  installed {src.name}")
        else:
            lines.append(f"  already there: {src.name}")
    if sys.platform.startswith("linux") and shutil.which("fc-cache"):
        os.system("fc-cache -f >/dev/null 2>&1")
    lines.append(f"Fonts are in {target}. Restart Word (or any open program) to see them.")
    return lines


def _register_windows(path: Path) -> None:
    """Per-user fonts on Windows also need a registry entry."""
    if not sys.platform.startswith("win"):
        return
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows NT\CurrentVersion\Fonts", 0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, f"{path.stem} (TrueType)", 0, winreg.REG_SZ, str(path))
        winreg.CloseKey(key)
    except OSError:
        pass
