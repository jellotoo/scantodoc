"""Measurements taken directly from a page image.

Tesseract tells us *what* the words are and where; it does not say whether
they are bold, italic, underlined or coloured. These functions look at the
pixels of each word to work that out.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = 400_000_000


@dataclass
class PageImage:
    rgb: np.ndarray  # H x W x 3 uint8
    gray: np.ndarray  # H x W uint8
    threshold: int  # gray values below this count as ink

    @property
    def height(self) -> int:
        return self.gray.shape[0]

    @property
    def width(self) -> int:
        return self.gray.shape[1]

    @property
    def ink(self) -> np.ndarray:
        return self.gray < self.threshold


def otsu(gray: np.ndarray) -> int:
    hist = np.bincount(gray.ravel(), minlength=256).astype(np.float64)
    total = hist.sum()
    if total == 0:
        return 128
    levels = np.arange(256)
    w0 = np.cumsum(hist)
    w1 = total - w0
    m0 = np.cumsum(hist * levels)
    mt = m0[-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        between = (mt * w0 / total - m0) ** 2 / (w0 * w1)
    between[~np.isfinite(between)] = 0
    return int(np.argmax(between))


def load_page(path: Path | str) -> PageImage:
    img = Image.open(path).convert("RGB")
    rgb = np.asarray(img)
    gray = np.asarray(img.convert("L"))
    t = otsu(gray)
    # Keep the threshold away from extremes on nearly blank pages.
    t = int(min(max(t, 80), 200))
    return PageImage(rgb=rgb, gray=gray, threshold=t)


def _runs_1d(row: np.ndarray) -> np.ndarray:
    """Lengths of consecutive True runs in a 1-D boolean array."""
    if not row.any():
        return np.empty(0, dtype=np.int32)
    padded = np.concatenate(([False], row, [False]))
    diff = np.diff(padded.astype(np.int8))
    starts = np.flatnonzero(diff == 1)
    ends = np.flatnonzero(diff == -1)
    return ends - starts


def longest_run(row: np.ndarray) -> int:
    runs = _runs_1d(row)
    return int(runs.max()) if runs.size else 0


def stroke_width(mask: np.ndarray) -> float:
    """Typical thickness of vertical strokes, from horizontal ink runs."""
    h, w = mask.shape
    if h < 4 or w < 2:
        return 0.0
    lengths = []
    # Sample the middle band of rows, where stems are and serifs are not.
    for y in range(int(h * 0.3), max(int(h * 0.7), int(h * 0.3) + 1)):
        runs = _runs_1d(mask[y])
        if runs.size:
            lengths.append(runs[runs < max(3, h * 0.6)])
    if not lengths:
        return 0.0
    allruns = np.concatenate(lengths)
    if allruns.size == 0:
        return 0.0
    return float(np.median(allruns))


def slant(mask: np.ndarray) -> float:
    """Shear that makes the strokes most upright; ~0 for roman, ~0.2 for italic."""
    h, w = mask.shape
    if h < 8 or w < 8 or mask.sum() < 30:
        return 0.0
    ys, xs = np.nonzero(mask)
    yc = h / 2.0
    best_s, best_score = 0.0, -1.0
    for s in np.arange(-0.15, 0.41, 0.025):
        shifted = np.round(xs + s * (ys - yc)).astype(np.int64)
        shifted -= shifted.min()
        hist = np.bincount(shifted)
        score = float((hist.astype(np.float64) ** 2).sum())
        if score > best_score:
            best_score, best_s = score, float(s)
    return best_s


def _box(page: PageImage, left: int, top: int, right: int, bottom: int) -> tuple[int, int, int, int]:
    return max(0, left), max(0, top), min(page.width, right), min(page.height, bottom)


def word_mask(page: PageImage, left: int, top: int, right: int, bottom: int) -> np.ndarray:
    x0, y0, x1, y1 = _box(page, left, top, right, bottom)
    return page.gray[y0:y1, x0:x1] < page.threshold


def ink_color(page: PageImage, left: int, top: int, right: int, bottom: int) -> str | None:
    """The colour of the strokes, or None for black/grey ink."""
    x0, y0, x1, y1 = _box(page, left, top, right, bottom)
    gray = page.gray[y0:y1, x0:x1]
    if gray.size == 0:
        return None
    rgb = page.rgb[y0:y1, x0:x1].reshape(-1, 3).astype(np.int32)
    g = gray.reshape(-1)
    ink = g < page.threshold
    if ink.sum() < 8:
        return None
    # The cores of the strokes: the darkest half of the ink pixels.
    cutoff = np.percentile(g[ink], 50)
    core = rgb[ink & (g <= cutoff)]
    if core.size == 0:
        return None
    med = np.median(core, axis=0)
    chroma = med.max() - med.min()
    if chroma < 45:
        return None
    return "#{:02X}{:02X}{:02X}".format(*(int(v) for v in med))


def has_line_below(page: PageImage, left: int, top: int, right: int, bottom: int, em: float) -> bool:
    """An underline: a long thin horizontal ink line at or just under the word's bottom."""
    width = right - left
    if width < 6:
        return False
    y_start = int(bottom - 0.12 * em)
    y_end = int(bottom + 0.22 * em)
    x0, y0, x1, y1 = _box(page, left, y_start, right, y_end)
    region = page.gray[y0:y1, x0:x1] < page.threshold
    for row in region:
        if longest_run(row) >= 0.85 * width:
            return True
    return False


def has_line_through(page: PageImage, left: int, top: int, right: int, bottom: int, em: float) -> bool:
    width = right - left
    if width < 6:
        return False
    mid = bottom - 0.28 * em
    x0, y0, x1, y1 = _box(page, left, int(mid - 0.1 * em), right, int(mid + 0.1 * em))
    region = page.gray[y0:y1, x0:x1] < page.threshold
    return any(longest_run(row) >= 0.85 * width for row in region)


@dataclass
class Rule:
    """A printed straight line (table border, separator)."""

    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def horizontal(self) -> bool:
        return (self.x1 - self.x0) >= (self.y1 - self.y0)


def find_rules(page: PageImage, min_len_frac: float = 0.08, max_thick: int = 12) -> list[Rule]:
    """Find long straight horizontal and vertical lines on the page."""
    ink = page.ink
    h, w = ink.shape
    rules: list[Rule] = []
    min_h = int(w * min_len_frac)
    for y in range(h):
        row = ink[y]
        if row.sum() < min_h:
            continue
        padded = np.concatenate(([False], row, [False]))
        diff = np.diff(padded.astype(np.int8))
        for s, e in zip(np.flatnonzero(diff == 1), np.flatnonzero(diff == -1)):
            if e - s >= min_h:
                rules.append(Rule(int(s), y, int(e), y + 1))
    min_v = int(h * min_len_frac * 0.5)
    col_sums = ink.sum(axis=0)
    for x in np.flatnonzero(col_sums >= min_v):
        col = ink[:, x]
        padded = np.concatenate(([False], col, [False]))
        diff = np.diff(padded.astype(np.int8))
        for s, e in zip(np.flatnonzero(diff == 1), np.flatnonzero(diff == -1)):
            if e - s >= min_v:
                rules.append(Rule(int(x), int(s), int(x) + 1, int(e)))
    return _merge_rules(rules, max_thick)


def _merge_rules(rules: list[Rule], max_thick: int) -> list[Rule]:
    """Merge the one-pixel slices of each thick line into a single rule."""
    merged: list[Rule] = []
    for horizontal in (True, False):
        group = sorted(
            (r for r in rules if r.horizontal == horizontal),
            key=(lambda r: (r.y0, r.x0)) if horizontal else (lambda r: (r.x0, r.y0)),
        )
        current: list[Rule] = []
        for r in group:
            placed = False
            for m in current:
                if horizontal:
                    near = r.y0 - m.y1 <= 2 and abs(r.x0 - m.x0) < 12 and abs(r.x1 - m.x1) < 12
                else:
                    near = r.x0 - m.x1 <= 2 and abs(r.y0 - m.y0) < 12 and abs(r.y1 - m.y1) < 12
                if near:
                    m.x0, m.y0 = min(m.x0, r.x0), min(m.y0, r.y0)
                    m.x1, m.y1 = max(m.x1, r.x1), max(m.y1, r.y1)
                    placed = True
                    break
            if not placed:
                current.append(Rule(r.x0, r.y0, r.x1, r.y1))
        for m in current:
            thick = (m.y1 - m.y0) if horizontal else (m.x1 - m.x0)
            if thick <= max_thick:
                merged.append(m)
    return merged


def ink_components(mask: np.ndarray, min_cells: int = 6) -> list[tuple[int, int, int, int]]:
    """Bounding boxes (x0, y0, x1, y1) of connected True areas in a small grid."""
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    boxes = []
    for y in range(h):
        for x in range(w):
            if not mask[y, x] or seen[y, x]:
                continue
            stack = [(y, x)]
            seen[y, x] = True
            x0 = x1 = x
            y0 = y1 = y
            count = 0
            while stack:
                cy, cx = stack.pop()
                count += 1
                x0, x1, y0, y1 = min(x0, cx), max(x1, cx), min(y0, cy), max(y1, cy)
                for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            if count >= min_cells:
                boxes.append((x0, y0, x1 + 1, y1 + 1))
    return boxes
