"""The free, offline reader: Tesseract OCR plus ScanToDoc's own layout analysis."""

from __future__ import annotations

import io
import statistics

from PIL import Image

from .. import layout, measure, tesseract
from ...text import count_strong
from .base import PageInput, PageResult

LOCAL_VERSION = "local-2"
RETRY_BELOW = 75.0  # re-read a line with one language when its confidence is below this
ARTIFACTS = {"|", "\\", "/", "_", "~", "¦"}


class LocalReader:
    name = "local"

    def __init__(self, languages: str = "eng+heb"):
        self.languages = languages

    def cache_key(self) -> str:
        langs = tesseract.usable_languages(self.languages)
        return f"{LOCAL_VERSION}|{tesseract.version()}|{langs}"

    def read(self, page: PageInput) -> PageResult:
        ocr_words = tesseract.run_tsv(page.image_path, self.languages, dpi=page.dpi)
        ocr_words = self._retry_weak_lines(page, ocr_words)
        words = [
            layout.Word(
                text=w.text,
                x0=w.left,
                y0=w.top,
                x1=w.right,
                y1=w.bottom,
                conf=w.conf,
                key=(w.block, w.par, w.line),
            )
            for w in ocr_words
            if not (w.text in ARTIFACTS and w.conf < 90)
        ]
        img = measure.load_page(page.image_path)
        result = layout.analyze(words, img, page.dpi, page.width_px, page.height_px)
        return PageResult(blocks=result.blocks, regions=result.regions, quality=result.quality, reader="local")

    def _retry_weak_lines(self, page: PageInput, words: list[tesseract.OcrWord]) -> list[tesseract.OcrWord]:
        """Mixed-language OCR sometimes reads a Hebrew line as Latin garbage (or the
        reverse). Re-read such lines with just the line's own script and keep
        whichever reading Tesseract is more confident about."""
        lines: dict[tuple, list[tesseract.OcrWord]] = {}
        for w in words:
            lines.setdefault((w.block, w.par, w.line), []).append(w)
        installed = set(tesseract.languages())
        wanted = [lang for lang in self.languages.replace(",", "+").split("+") if lang in installed]
        if len(wanted) < 2:
            return words
        image = None
        out: list[tesseract.OcrWord] = []
        for key, ws in lines.items():
            conf = _mean_conf(ws)
            if conf >= RETRY_BELOW and not _has_garbled_latin(ws):
                out.extend(ws)
                continue
            if image is None:
                image = Image.open(page.image_path).convert("L")
            best = ws
            best_conf = conf
            garbled = _has_garbled_latin(ws)
            for langs in _single_script_choices(ws, wanted):
                cand = _ocr_line(image, ws, langs, page.dpi, key)
                if not cand:
                    continue
                cand_conf = _mean_conf(cand)
                # Hebrew with nikud scores lower than Latin garbage does, so a clean
                # all-Hebrew reading may win with a somewhat lower score.
                rescued = garbled and _hebrew_share(cand) > 0.8 and cand_conf >= best_conf - 25
                if cand_conf > best_conf + 5 or rescued:
                    best, best_conf = cand, cand_conf
                    garbled = False
            out.extend(best)
        return out


def _mean_conf(ws: list[tesseract.OcrWord]) -> float:
    vals = [(w.conf, len(w.text)) for w in ws if w.conf >= 0]
    if not vals:
        return 0.0
    return sum(c * n for c, n in vals) / sum(n for _, n in vals)


def _hebrew_share(ws: list[tesseract.OcrWord]) -> float:
    rtl = ltr = 0
    for w in ws:
        r, l_ = count_strong(w.text)
        rtl += r
        ltr += l_
    return rtl / max(rtl + ltr, 1)


def _has_garbled_latin(ws: list[tesseract.OcrWord]) -> bool:
    """Short, unsure Latin 'words' inside a mostly-Hebrew line are usually
    Hebrew letters (often with nikud) that were read with the English model."""
    if _hebrew_share(ws) < 0.4:
        return False
    for w in ws:
        r, l_ = count_strong(w.text)
        if l_ and not r and len(w.text) <= 5 and w.conf < 80:
            return True
    return False


def _single_script_choices(ws: list[tesseract.OcrWord], wanted: list[str]) -> list[str]:
    rtl = ltr = 0
    for w in ws:
        r, l_ = count_strong(w.text)
        rtl += r
        ltr += l_
    hebrew_script = [lang for lang in wanted if lang in ("heb", "yid", "Hebrew")]
    latin = [lang for lang in wanted if lang not in hebrew_script]
    choices = []
    # A garbled Hebrew line often comes back as capital Latin letters, so try
    # Hebrew for any weak line when it is installed, then Latin.
    if hebrew_script:
        choices.append("+".join(hebrew_script))
    if latin and ltr >= rtl:
        choices.append("+".join(latin))
    return choices


def _ocr_line(image: Image.Image, ws: list[tesseract.OcrWord], langs: str, dpi: int, key: tuple) -> list[tesseract.OcrWord]:
    x0 = min(w.left for w in ws)
    y0 = min(w.top for w in ws)
    x1 = max(w.right for w in ws)
    y1 = max(w.bottom for w in ws)
    pad = int(max(y1 - y0, 10) * 0.35)
    box = (max(0, x0 - pad), max(0, y0 - pad), min(image.width, x1 + pad), min(image.height, y1 + pad))
    crop = image.crop(box)
    buf = io.BytesIO()
    crop.save(buf, format="PNG")
    try:
        found = tesseract.run_tsv(buf.getvalue(), langs, psm=7, timeout=60, dpi=dpi)
    except RuntimeError:
        return []
    block, par, line = key
    out = []
    for w in found:
        w.left += box[0]
        w.top += box[1]
        w.block, w.par, w.line = block, par, line
        out.append(w)
    heights = [w.height for w in out]
    if heights and statistics.median(heights) < 0.4 * (y1 - y0):
        return []  # read something tiny (noise), not the line
    return out
