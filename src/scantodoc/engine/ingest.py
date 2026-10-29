"""Turn the user's input (PDFs, folders, loose page images) into page images.

Every page is rendered to a 300 DPI image, which is what the readers and the
side-by-side view use. If a PDF page already carries real text, its words
(with fonts, sizes and colours) are extracted too.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import pymupdf
from PIL import Image, ImageOps

from ..text import has_rtl, looks_visual_order

PDF_EXT = {".pdf"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".gif"}
DEFAULT_DPI = 300
JPEG_QUALITY = 90


@dataclass
class SourcePage:
    path: Path
    page: int  # 0-based page (or TIFF frame) within the file
    kind: str  # "pdf" or "image"


def natural_key(p: Path) -> list:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]


def collect_inputs(paths: Iterable[Path | str]) -> list[Path]:
    """Expand folders and keep only files ScanToDoc can read, in natural order."""
    out: list[Path] = []
    for raw in paths:
        p = Path(raw).expanduser()
        if p.is_dir():
            kids = [c for c in p.iterdir() if c.is_file() and c.suffix.lower() in PDF_EXT | IMAGE_EXT]
            out.extend(sorted(kids, key=natural_key))
        elif p.is_file() and p.suffix.lower() in PDF_EXT | IMAGE_EXT:
            out.append(p)
        elif not p.exists():
            raise FileNotFoundError(f"Not found: {p}")
        else:
            raise ValueError(f"Not a PDF or image file: {p}")
    return out


def list_pages(files: list[Path]) -> list[SourcePage]:
    pages: list[SourcePage] = []
    for f in files:
        if f.suffix.lower() in PDF_EXT:
            with pymupdf.open(f) as doc:
                if doc.needs_pass:
                    raise ValueError(f"{f.name} is password-protected; please remove the password first.")
                pages.extend(SourcePage(f, i, "pdf") for i in range(doc.page_count))
        else:
            with Image.open(f) as im:
                frames = getattr(im, "n_frames", 1)
            pages.extend(SourcePage(f, i, "image") for i in range(frames))
    return pages


def parse_page_range(spec: Optional[str], total: int) -> list[int]:
    """'1-3,7' -> [0, 1, 2, 6] (pages are numbered from 1 for people)."""
    if not spec:
        return list(range(total))
    chosen: list[int] = []
    for part in spec.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            start = int(a) if a else 1
            end = int(b) if b else total
            chosen.extend(range(start - 1, min(end, total)))
        else:
            n = int(part)
            if 1 <= n <= total:
                chosen.append(n - 1)
    return sorted(set(i for i in chosen if 0 <= i < total))


@dataclass
class RenderedPage:
    image: Path
    width_px: int
    height_px: int
    dpi: int
    image_hash: str
    text_layer: Optional[dict]


def render(src: SourcePage, out_image: Path, dpi: int = DEFAULT_DPI) -> RenderedPage:
    out_image.parent.mkdir(parents=True, exist_ok=True)
    text_layer = None
    if src.kind == "pdf":
        with pymupdf.open(src.path) as doc:
            page = doc[src.page]
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            text_layer = extract_text_layer(page, dpi)
        used_dpi = dpi
    else:
        with Image.open(src.path) as im:
            if getattr(im, "n_frames", 1) > 1:
                im.seek(src.page)
            img = ImageOps.exif_transpose(im.convert("RGB"))
            used_dpi = _image_dpi(im, img)
        if used_dpi < 250:
            # Tesseract and the font-size estimates both work best near 300 DPI.
            scale = DEFAULT_DPI / used_dpi
            img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
            used_dpi = DEFAULT_DPI
    if _is_grayscale(img):
        img = img.convert("L")
    img.save(out_image, format="JPEG", quality=JPEG_QUALITY, dpi=(used_dpi, used_dpi))
    digest = hashlib.sha1(out_image.read_bytes()).hexdigest()
    if text_layer is not None:
        out_image.with_suffix(".text.json").write_text(json.dumps(text_layer, ensure_ascii=False), encoding="utf-8")
    return RenderedPage(out_image, img.width, img.height, used_dpi, digest, text_layer)


def _image_dpi(original: Image.Image, img: Image.Image) -> int:
    info = original.info.get("dpi")
    if info and info[0] and info[0] > 30:
        return int(round(float(info[0])))
    # No DPI recorded: assume the long side of the picture is a Letter/A4 page.
    return max(72, int(round(max(img.width, img.height) / 11.0)))


def _is_grayscale(img: Image.Image) -> bool:
    import numpy as np

    # Look at a third-size copy so even one small coloured word is noticed.
    small = np.asarray(img.convert("RGB").resize((max(img.width // 3, 1), max(img.height // 3, 1))), dtype=np.int16)
    spread = small.max(axis=2) - small.min(axis=2)
    return int((spread >= 40).sum()) < 20


def extract_text_layer(page: "pymupdf.Page", dpi: int) -> Optional[dict]:
    """Words of a PDF page's own text, in pixel coordinates at `dpi`.

    Returns None when the page has no usable text (a pure scan).
    """
    scale = dpi / 72.0
    raw = page.get_text("rawdict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_MEDIABOX_CLIP)
    words = []
    total_chars = bad_chars = 0
    glyphless = 0
    for b_i, block in enumerate(raw.get("blocks", [])):
        if block.get("type") != 0:
            continue
        for l_i, line in enumerate(block.get("lines", [])):
            for span in line.get("spans", []):
                font = span.get("font", "")
                if "GlyphLess" in font:
                    glyphless += 1
                flags = span.get("flags", 0)
                color = span.get("color", 0)
                hexcol = "#{:06X}".format(color)
                r, g, bl = (color >> 16) & 255, (color >> 8) & 255, color & 255
                if max(r, g, bl) - min(r, g, bl) < 45:
                    hexcol = None
                current: list[dict] = []
                for ch in span.get("chars", []):
                    c = ch.get("c", "")
                    total_chars += 1
                    if c == "�":
                        bad_chars += 1
                    if c.isspace():
                        if current:
                            words.append(_word(current, span, font, flags, hexcol, b_i, l_i, scale))
                            current = []
                        continue
                    current.append(ch)
                if current:
                    words.append(_word(current, span, font, flags, hexcol, b_i, l_i, scale))
    meaningful = sum(len(w["text"]) for w in words)
    if meaningful < 20 or (total_chars and bad_chars / total_chars > 0.2):
        return None
    all_text = " ".join(w["text"] for w in words)
    visual = has_rtl(all_text) and looks_visual_order(all_text)
    if visual:
        for w in words:
            if has_rtl(w["text"]):
                w["text"] = w["text"][::-1]
    return {
        "words": words,
        "ocr_layer": glyphless > 0,  # an invisible layer from earlier OCR: text yes, styling no
        "visual_order_fixed": visual,
        "text": all_text,
    }


def _word(chars: list[dict], span: dict, font: str, flags: int, color: Optional[str], b: int, ln: int, scale: float) -> dict:
    x0 = min(c["bbox"][0] for c in chars) * scale
    y0 = min(c["bbox"][1] for c in chars) * scale
    x1 = max(c["bbox"][2] for c in chars) * scale
    y1 = max(c["bbox"][3] for c in chars) * scale
    lower = font.lower()
    bold = bool(flags & 16) or any(k in lower for k in ("bold", "black", "heavy", "semibold", "demi"))
    italic = bool(flags & 2) or "italic" in lower or "oblique" in lower
    if flags & 8 or "mono" in lower or "courier" in lower:
        category = "monospace"
    elif flags & 4 or any(k in lower for k in ("times", "serif", "garamond", "georgia", "frank", "david", "roman", "minion", "book")):
        category = "serif"
    else:
        category = "sans-serif"
    if "rashi" in lower:
        category = "rashi"
    return {
        "text": "".join(c["c"] for c in chars),
        "bbox": [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)],
        "size": round(span.get("size", 0), 2),
        "font": font,
        "bold": bold,
        "italic": italic,
        "superscript": bool(flags & 1),
        "color": color,
        "category": category,
        "key": [b, ln],
    }
