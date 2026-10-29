"""Run a ScanToDoc command, installing ScanToDoc first if needed.

Usage:  python3 run.py COMMAND [OPTIONS]      e.g.  python3 run.py convert book.pdf -f docx
        python3 run.py --help
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import setup  # noqa: E402


def python_with_scantodoc() -> str | None:
    vpy = setup.venv_python()
    if vpy.exists() and setup.works(vpy):
        return str(vpy)
    if setup.works(sys.executable):
        return sys.executable
    return None


def main() -> int:
    py = python_with_scantodoc()
    if py is None:
        if setup.main() != 0:
            return 1
        py = python_with_scantodoc()
        if py is None:
            return 1
    return subprocess.run([py, "-m", "scantodoc", *sys.argv[1:]]).returncode


if __name__ == "__main__":
    sys.exit(main())
