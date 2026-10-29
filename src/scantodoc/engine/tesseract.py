"""A small wrapper around the Tesseract OCR program (free, runs offline).

We call the ``tesseract`` executable directly and read its TSV output, which
lists every recognised word with its position and a 0-100 confidence score.
"""

from __future__ import annotations

import csv
import functools
import io
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

BIDI_CONTROLS = dict.fromkeys(map(ord, "\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"))

WINDOWS_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
]
MAC_PATHS = ["/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract"]


# ScanToDoc runs several pages at once; letting every Tesseract process also
# start one thread per CPU core makes them fight and run ~100x slower.
_ENV = {**os.environ, "OMP_THREAD_LIMIT": "1"}


class TesseractMissing(RuntimeError):
    pass


@dataclass
class OcrWord:
    text: str
    left: int
    top: int
    width: int
    height: int
    conf: float
    block: int
    par: int
    line: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height


@functools.lru_cache(maxsize=1)
def find_tesseract() -> str | None:
    env = os.environ.get("TESSERACT_CMD") or os.environ.get("SCANTODOC_TESSERACT")
    if env and Path(env).exists():
        return env
    found = shutil.which("tesseract")
    if found:
        return found
    for path in WINDOWS_PATHS + MAC_PATHS:
        if Path(path).exists():
            return path
    return None


def require_tesseract() -> str:
    exe = find_tesseract()
    if not exe:
        raise TesseractMissing(
            "Tesseract OCR is not installed, so the free local reader cannot run. "
            "See the README section 'Install Tesseract' (Windows: the UB Mannheim installer; "
            "Mac: 'brew install tesseract tesseract-lang'), or choose the Claude reader instead."
        )
    return exe


@functools.lru_cache(maxsize=1)
def version() -> str:
    exe = find_tesseract()
    if not exe:
        return ""
    out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30)
    first = (out.stdout or out.stderr).splitlines()
    return first[0].strip() if first else ""


@functools.lru_cache(maxsize=1)
def languages() -> tuple[str, ...]:
    exe = find_tesseract()
    if not exe:
        return ()
    out = subprocess.run([exe, "--list-langs"], capture_output=True, text=True, timeout=30)
    lines = (out.stdout or out.stderr).splitlines()
    return tuple(sorted(line.strip() for line in lines[1:] if line.strip()))


def usable_languages(requested: str) -> str:
    """Keep only the requested languages that are installed; fall back to 'eng'."""
    have = set(languages())
    wanted = [lang for lang in requested.replace(",", "+").split("+") if lang]
    keep = [lang for lang in wanted if lang in have]
    if not keep:
        keep = ["eng"] if "eng" in have or not have else [sorted(have)[0]]
    return "+".join(keep)


def run_tsv(
    image: Path | bytes, langs: str = "eng+heb", psm: int = 3, timeout: int = 600, dpi: int | None = None
) -> list[OcrWord]:
    """OCR an image file (or PNG bytes) and return its words."""
    exe = require_tesseract()
    langs = usable_languages(langs)
    source = "stdin" if isinstance(image, (bytes, bytearray)) else str(image)
    cmd = [exe, source, "stdout", "-l", langs, "--psm", str(psm), "-c", "preserve_interword_spaces=0"]
    if dpi:
        cmd += ["--dpi", str(dpi)]
    cmd.append("tsv")
    proc = subprocess.run(
        cmd,
        input=image if isinstance(image, (bytes, bytearray)) else None,
        capture_output=True,
        timeout=timeout,
        env=_ENV,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Tesseract failed: {proc.stderr.decode('utf-8', 'replace')[-500:]}")
    text = proc.stdout.decode("utf-8", "replace")
    words: list[OcrWord] = []
    reader = csv.DictReader(io.StringIO(text), delimiter="\t", quoting=csv.QUOTE_NONE)
    for row in reader:
        if row.get("level") != "5":
            continue
        word = (row.get("text") or "").translate(BIDI_CONTROLS).strip()
        if not word:
            continue
        try:
            words.append(
                OcrWord(
                    text=word,
                    left=int(row["left"]),
                    top=int(row["top"]),
                    width=int(row["width"]),
                    height=int(row["height"]),
                    conf=float(row["conf"]),
                    block=int(row["block_num"]),
                    par=int(row["par_num"]),
                    line=int(row["line_num"]),
                )
            )
        except (KeyError, ValueError):
            continue
    return words
