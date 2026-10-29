"""Install ScanToDoc for this skill (once). Uses only the Python standard library.

It installs into its own virtual environment (~/ScanToDoc/venv, or
$SCANTODOC_HOME/venv) so nothing else on the computer changes. Where a virtual
environment cannot be made, it falls back to a per-user install.

Usage:  python3 setup.py [--force]
"""

from __future__ import annotations

import glob
import os
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
REPO_GIT = "git+https://github.com/jellotoo/scantodoc.git"


def home() -> Path:
    return Path(os.environ.get("SCANTODOC_HOME") or Path.home() / "ScanToDoc")


def venv_python() -> Path:
    v = home() / "venv"
    return v / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def source() -> str:
    """Where to install from: the wheel shipped in the skill, a checkout this skill
    sits in, or the GitHub repository."""
    wheels = sorted(glob.glob(str(SKILL / "wheels" / "scantodoc-*.whl")))
    if wheels:
        return wheels[-1]
    for parent in SKILL.parents:
        if (parent / "pyproject.toml").exists() and (parent / "src" / "scantodoc").is_dir():
            return str(parent)
    return REPO_GIT


def works(python: Path | str) -> bool:
    try:
        r = subprocess.run([str(python), "-m", "scantodoc", "--version"], capture_output=True, text=True, timeout=120)
    except OSError:
        return False
    return r.returncode == 0


def pip(python: Path | str, *args: str) -> bool:
    cmd = [str(python), "-m", "pip", "install", "--quiet", "--disable-pip-version-check", *args]
    print("  " + " ".join(cmd), flush=True)
    return subprocess.run(cmd).returncode == 0


def main() -> int:
    force = "--force" in sys.argv
    vpy = venv_python()
    if not force and vpy.exists() and works(vpy):
        print(f"ScanToDoc is installed ({vpy}).")
        return 0
    src = source()
    print(f"Installing ScanToDoc from {src} ...", flush=True)
    home().mkdir(parents=True, exist_ok=True)
    if not vpy.exists():
        subprocess.run([sys.executable, "-m", "venv", str(home() / "venv")], capture_output=True)
    if vpy.exists() and pip(vpy, "--upgrade", src) and works(vpy):
        print(f"Done. ScanToDoc runs with: {vpy} -m scantodoc")
        return 0
    print("A separate environment could not be used; installing for this user instead.", flush=True)
    for extra in (["--user"], ["--user", "--break-system-packages"], ["--break-system-packages"]):
        if pip(sys.executable, "--upgrade", *extra, src) and works(sys.executable):
            print(f"Done. ScanToDoc runs with: {sys.executable} -m scantodoc")
            return 0
    print(
        "Could not install ScanToDoc. It needs Python 3.10+ and internet access to the Python "
        "package index (pypi.org).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
