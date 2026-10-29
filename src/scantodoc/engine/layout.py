"""Turn positioned words into structured blocks (the local, no-AI path).

Input: words with positions, from Tesseract or from a PDF's own text layer.
Output: the blocks of the document model - headings, paragraphs, list items,
tables, figures, captions, footnotes, headers and footers - with alignment,
indentation, font size and run formatting worked out from geometry and from
the page pixels.

Everything here is heuristic (rules of thumb tuned on real layouts). It is the
reason the local reader is free; it is also why the Claude reader does better
on unusual pages.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from ..model import Block, Cell, Figure, Region, Run, Table
from ..text import char_class, count_strong, dehyphenate_join, ends_sentence, is_hebrew
from . import measure as M

UNCERTAIN_CONF = 75.0

# ------------------------------------------------------------------ word geometry

_LATIN_X = set("acemnorsuvwxz")
_LATIN_CAP = set("ABCDEFGHIJKLMNOPRSTUVWXYZ0123456789")
_LATIN_ASC = set("bdfhkl")
_LATIN_DESC = set("gjpqy")
_HEB_ASC = set("ל")
_HEB_DESC = set("קךןףץ")
_NIKUD_BELOW = set(chr(c) for c in range(0x05B0, 0x05BC)) | {"\u05C2", "\u05C1", "\u05C7"}


def expected_height_em(text: str) -> Optional[float]:
    """How tall (in ems) the ink of this word should be, from its letters.

    Measured on common book faces: lowercase x-height about 0.50 em, capitals
    and digits 0.665, ascenders 0.71, descenders 0.21 below the baseline;
    Hebrew letters 0.53, with lamed rising to 0.755 and final letters
    descending 0.225.
    """
    top, bottom, known = 0.0, 0.0, False
    for ch in text:
        if ch in _LATIN_X:
            top = max(top, 0.50)
        elif ch == "t":
            top = max(top, 0.62)
        elif ch in _LATIN_CAP:
            top = max(top, 0.665)
        elif ch in _LATIN_ASC:
            top = max(top, 0.71)
        elif ch in "ij":
            top = max(top, 0.70)
        elif ch in _LATIN_DESC:
            top = max(top, 0.50)
            bottom = min(bottom, -0.21 if ch != "j" else -0.21)
        elif ch == "Q":
            top = max(top, 0.665)
        elif is_hebrew(ch):
            if ch in _NIKUD_BELOW:
                bottom = min(bottom, -0.16)
                continue
            if "\u05D0" <= ch <= "\u05EA":
                top = max(top, 0.755 if ch in _HEB_ASC else 0.53)
                if ch in _HEB_DESC:
                    bottom = min(bottom, -0.225)
            else:
                continue
        else:
            continue
        known = True
    if not known:
        return None
    return top - bottom


@dataclass
class Word:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    conf: Optional[float] = None
    key: tuple = ()  # line grouping key from the source
    em: float = 0.0  # estimated em size in pixels
    size_pt: Optional[float] = None  # exact size when known (text layer)
    stroke_a: float = 0.0  # stroke thickness from ink area / outline (px)
    stroke_b: float = 0.0  # stroke thickness from ink runs (px)
    slant: float = 0.0
    bold: Optional[bool] = None
    italic: Optional[bool] = None
    underline: bool = False
    strike: bool = False
    superscript: bool = False
    subscript: bool = False
    color: Optional[str] = None
    font_category: Optional[str] = None
    rtl: bool = False

    @property
    def w(self) -> float:
        return self.x1 - self.x0

    @property
    def h(self) -> float:
        return self.y1 - self.y0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass
class Line:
    words: list[Word]
    rtl: bool = False
    x0: float = 0
    y0: float = 0
    x1: float = 0
    y1: float = 0
    em: float = 0.0
    bold_frac: float = 0.0
    group: int = 0

    def finish(self) -> "Line":
        self.x0 = min(w.x0 for w in self.words)
        self.x1 = max(w.x1 for w in self.words)
        self.y0 = min(w.y0 for w in self.words)
        self.y1 = max(w.y1 for w in self.words)
        ems = [w.em for w in self.words if w.em > 0]
        self.em = statistics.median(ems) if ems else max(self.y1 - self.y0, 1)
        nb = sum(len(w.text) for w in self.words if w.bold)
        total = sum(len(w.text) for w in self.words) or 1
        self.bold_frac = nb / total
        return self

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def baseline(self) -> float:
        flat = [w.y1 for w in self.words if not any(c in _LATIN_DESC or c in _HEB_DESC for c in w.text)]
        if flat:
            return statistics.median(flat)
        return self.y1 - 0.21 * self.em

    @property
    def start(self) -> float:
        return self.x1 if self.rtl else self.x0

    @property
    def end(self) -> float:
        return self.x0 if self.rtl else self.x1

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def width(self) -> float:
        return self.x1 - self.x0


# ------------------------------------------------------------------ measuring words


def _area_stroke(mask: np.ndarray) -> float:
    """Average stroke thickness = 2 x ink area / outline length."""
    area = int(mask.sum())
    if area == 0:
        return 0.0
    p = np.pad(mask, 1)
    inner = p[1:-1, 1:-1] & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
    outline = area - int(inner.sum())
    return 2.0 * area / max(outline, 1)


def _run_stroke(mask: np.ndarray) -> float:
    """Trimmed mean of horizontal ink runs across the middle of the word."""
    h = mask.shape[0]
    lengths = []
    for y in range(int(h * 0.3), max(int(h * 0.7), int(h * 0.3) + 1)):
        runs = M._runs_1d(mask[y])
        if runs.size:
            lengths.append(runs[runs < max(3, h * 0.6)])
    if not lengths:
        return 0.0
    allruns = np.concatenate(lengths)
    if allruns.size < 3:
        return float(allruns.mean()) if allruns.size else 0.0
    lo, hi = np.percentile(allruns, [20, 80])
    keep = allruns[(allruns >= lo) & (allruns <= hi)]
    return float(keep.mean()) if keep.size else float(allruns.mean())


def measure_words(words: list[Word], page: Optional[M.PageImage], dpi: int) -> None:
    for w in words:
        rtl_n, ltr_n = count_strong(w.text)
        w.rtl = rtl_n > ltr_n
        if w.size_pt:
            w.em = w.size_pt * dpi / 72.0
        else:
            ratio = expected_height_em(w.text)
            if ratio:
                w.em = max(w.h, 1) / ratio
        if page is None:
            continue
        x0, y0, x1, y1 = int(w.x0), int(w.y0), int(w.x1), int(w.y1)
        if w.bold is None:
            # Styling unknown (OCR): read it from the pixels.
            mask = M.word_mask(page, x0, y0, x1, y1)
            w.stroke_a = _area_stroke(mask)
            # Latin type is weighted in its vertical stems, Hebrew in its horizontal bars.
            w.stroke_b = _run_stroke(mask.T if w.rtl else mask)
            w.slant = M.slant(mask)
            w.color = M.ink_color(page, x0, y0, x1, y1)
        em = w.em or w.h
        if w.w >= 0.6 * em and w.h >= 0.3 * em and any(c.isalnum() for c in w.text):
            w.underline = M.has_line_below(page, x0, y0, x1, y1, em)
            w.strike = (not w.underline) and M.has_line_through(page, x0, y0, x1, y1, em)


def _fill_missing_em(words: list[Word]) -> None:
    known = [w.em for w in words if w.em]
    fallback = statistics.median(known) if known else 40.0
    for w in words:
        if not w.em:
            w.em = fallback


BOLD_SCORE = 1.25


def decide_emphasis(lines: list[Line]) -> None:
    """Bold and italic, judged against the page's own typical stroke and slant.

    Strokes are compared relative to the size of type on their line, so a
    large heading is not called bold just for being large.
    """
    samples: dict[bool, list[tuple[float, float, int]]] = {False: [], True: []}
    for ln in lines:
        for w in ln.words:
            if w.bold is None and w.stroke_a > 0 and w.stroke_b > 0 and sum(c.isalpha() for c in w.text) >= 2:
                samples[w.rtl].append((w.stroke_a / ln.em, w.stroke_b / ln.em, len(w.text)))
    base: dict[bool, tuple[float, float]] = {}
    for script, vals in samples.items():
        if not vals:
            continue
        # The regular weight is the common one; take a low-middle percentile of each.
        a = _weighted_percentile([v[0] for v in vals], [v[2] for v in vals], 0.4)
        b = _weighted_percentile([v[1] for v in vals], [v[2] for v in vals], 0.4)
        base[script] = (a, b)
    for ln in lines:
        for w in ln.words:
            if w.bold is None:
                ref = base.get(w.rtl)
                if ref and w.stroke_a > 0 and w.stroke_b > 0 and ref[0] > 0 and ref[1] > 0:
                    score = ((w.stroke_a / ln.em / ref[0]) * (w.stroke_b / ln.em / ref[1])) ** 0.5
                    w.bold = score > BOLD_SCORE
                else:
                    w.bold = False
            if w.italic is None:
                letters = sum(1 for c in w.text if c.isalpha())
                w.italic = (not w.rtl) and letters >= 4 and w.slant >= 0.1


def _weighted_percentile(values: list[float], weights: list[int], q: float) -> float:
    pairs = sorted(zip(values, weights))
    total = sum(weights)
    acc = 0
    for v, wt in pairs:
        acc += wt
        if acc >= q * total:
            return v
    return pairs[-1][0]


def smooth_line_emphasis(line: Line) -> None:
    ws = line.words
    for attr in ("bold", "italic"):
        flags = [bool(getattr(w, attr)) for w in ws]
        # A short word between two emphasised neighbours is almost always emphasised too.
        for i in range(1, len(ws) - 1):
            if not flags[i] and flags[i - 1] and flags[i + 1] and len(ws[i].text) <= 3:
                setattr(ws[i], attr, True)
        total = sum(len(w.text) for w in ws)
        on = sum(len(w.text) for w, f in zip(ws, flags) if f)
        if len(ws) >= 2 and total and on / total >= 0.6:
            for w in ws:
                setattr(w, attr, True)
    # Colours that differ only by scanner noise are the same colour.
    for prev, cur in zip(ws, ws[1:]):
        if prev.color and cur.color and similar_color(prev.color, cur.color):
            cur.color = prev.color


def similar_color(a: Optional[str], b: Optional[str], tol: int = 40) -> bool:
    if a == b:
        return True
    if not a or not b:
        return False
    ra, ga, ba = (int(a[i : i + 2], 16) for i in (1, 3, 5))
    rb, gb, bb = (int(b[i : i + 2], 16) for i in (1, 3, 5))
    return abs(ra - rb) + abs(ga - gb) + abs(ba - bb) <= tol


def build_lines(words: list[Word]) -> list[Line]:
    groups: dict[tuple, list[Word]] = {}
    for w in words:
        groups.setdefault(w.key, []).append(w)
    lines = []
    for ws in groups.values():
        rtl_n = sum(len(w.text) for w in ws if w.rtl)
        ltr_n = sum(len(w.text) for w in ws if not w.rtl and any(char_class(c) == "L" for c in w.text))
        rtl = rtl_n > ltr_n
        lines.extend(_split_far_apart(order_words(ws, rtl), rtl))
    for line in lines:
        line.finish()
    return lines


def order_words(ws: list[Word], rtl: bool) -> list[Word]:
    """Put the words of one line into reading (logical) order.

    Right-to-left lines are read from the right, except that a run of
    consecutive left-to-right words (an English phrase inside Hebrew) keeps
    its own left-to-right order - and the same in reverse for Hebrew phrases
    inside English lines.
    """
    ws = sorted(ws, key=lambda w: -w.cx if rtl else w.cx)
    out: list[Word] = []
    i = 0
    while i < len(ws):
        if not _is_foreign(ws[i], rtl):
            out.append(ws[i])
            i += 1
            continue
        j = i
        while j < len(ws):
            if _is_foreign(ws[j], rtl):
                j += 1
            elif not _is_strong(ws[j]) and j + 1 < len(ws) and _is_foreign(ws[j + 1], rtl):
                j += 1  # a number or dash between two foreign words stays with them
            else:
                break
        out.extend(reversed(ws[i:j]))
        i = j
    return out


def _is_foreign(w: Word, rtl: bool) -> bool:
    return _is_strong(w) and w.rtl != rtl


def _is_strong(w: Word) -> bool:
    return any(char_class(c) != "N" for c in w.text)


VERTICAL_RULES: list[M.Rule] = []


def _split_far_apart(ws: list[Word], rtl: bool, rules: Optional[list[M.Rule]] = None) -> list[Line]:
    """Split a 'line' that really belongs to two columns: the words are far
    apart, a printed vertical rule runs between them, or the type size jumps."""
    if len(ws) < 2:
        return [Line(ws, rtl=rtl)]
    ems = [w.em for w in ws if w.em] or [max(w.h for w in ws)]
    em = statistics.median(ems)
    visual = sorted(ws, key=lambda w: w.x0)
    verticals = [r for r in (rules if rules is not None else VERTICAL_RULES) if not r.horizontal]
    pieces: list[list[Word]] = [[visual[0]]]
    for prev, cur in zip(visual, visual[1:]):
        gap = cur.x0 - prev.x1
        y0 = min(prev.y0, cur.y0)
        y1 = max(prev.y1, cur.y1)
        ruled = any(prev.x1 <= r.x0 <= cur.x0 and r.y0 <= y1 and r.y1 >= y0 for r in verticals)
        size_jump = prev.em and cur.em and abs(prev.em - cur.em) / max(prev.em, cur.em) > 0.18
        if gap > 2.2 * em or ruled or (gap > 0.9 * em and size_jump):
            pieces.append([])
        pieces[-1].append(cur)
    return [Line(order_words(p, rtl), rtl=rtl) for p in pieces]


# ------------------------------------------------------------------ tables


@dataclass
class Grid:
    x0: float
    y0: float
    x1: float
    y1: float
    xs: list[float]
    ys: list[float]
    verticals: list[M.Rule]


def find_tables(rules: list[M.Rule]) -> list[Grid]:
    horiz = [r for r in rules if r.horizontal]
    vert = [r for r in rules if not r.horizontal]
    grids: list[Grid] = []
    used = set()
    for i, h in enumerate(horiz):
        if i in used:
            continue
        group = [h]
        for j, other in enumerate(horiz):
            if j != i and j not in used and abs(other.x0 - h.x0) < 25 and abs(other.x1 - h.x1) < 25:
                group.append(other)
        if len(group) < 2:
            continue
        x0 = min(g.x0 for g in group)
        x1 = max(g.x1 for g in group)
        y0 = min(g.y0 for g in group)
        y1 = max(g.y1 for g in group)
        vs = [v for v in vert if x0 - 15 <= v.x0 <= x1 + 15 and v.y0 >= y0 - 15 and v.y1 <= y1 + 15]
        if len(vs) < 2 or len(group) < 3 and len(vs) < 3:
            # Two lines with nothing between them is a box or a separator, not a table.
            if len(group) < 3:
                continue
        for j, other in enumerate(horiz):
            if other in group:
                used.add(j)
        ys = _dedupe(sorted((g.y0 + g.y1) / 2 for g in group))
        xs = _dedupe(sorted([(v.x0 + v.x1) / 2 for v in vs] + [x0, x1]))
        if len(ys) >= 2 and len(xs) >= 2:
            grids.append(Grid(x0, y0, x1, y1, xs, ys, vs))
    return grids


def _dedupe(vals: list[float], tol: float = 12) -> list[float]:
    out: list[float] = []
    for v in vals:
        if not out or v - out[-1] > tol:
            out.append(v)
    return out


def _has_vertical(grid: Grid, x: float, y0: float, y1: float) -> bool:
    if abs(x - grid.x0) < 15 or abs(x - grid.x1) < 15:
        return True
    mid = (y0 + y1) / 2
    return any(abs((v.x0 + v.x1) / 2 - x) < 12 and v.y0 - 8 <= mid <= v.y1 + 8 for v in grid.verticals)


def table_block(grid: Grid, words: list[Word], rtl: bool, page_w: float, page_h: float) -> Block:
    rows: list[list[Cell]] = []
    nrows = len(grid.ys) - 1
    for r in range(nrows):
        top, bottom = grid.ys[r], grid.ys[r + 1]
        # Columns this row really has: merge across missing vertical lines.
        bounds = [grid.xs[0]]
        for x in grid.xs[1:-1]:
            if _has_vertical(grid, x, top, bottom):
                bounds.append(x)
        bounds.append(grid.xs[-1])
        row_cells: list[Cell] = []
        for c in range(len(bounds) - 1):
            left, right = bounds[c], bounds[c + 1]
            inside = [w for w in words if left <= w.cx <= right and top <= (w.y0 + w.y1) / 2 <= bottom]
            span = sum(1 for x in grid.xs if left - 2 < x < right + 2) - 1
            cell_lines = build_lines(inside) if inside else []
            cell_lines.sort(key=lambda ln: ln.y0)
            runs: list[Run] = []
            for k, ln in enumerate(cell_lines):
                if k:
                    runs.append(Run(text=" "))
                runs.extend(words_to_runs(ln.words))
            row_cells.append(
                Cell(runs=merge_runs(runs), colspan=max(span, 1), header=bool(runs) and all(rn.bold for rn in runs if rn.text.strip()))
            )
        if rtl:
            row_cells.reverse()
        rows.append(row_cells)
    return Block(
        type="table",
        table=Table(rows=rows, borders=True),
        direction="rtl" if rtl else "ltr",
        bbox=(grid.x0 / page_w, grid.y0 / page_h, grid.x1 / page_w, grid.y1 / page_h),
        runs=[],
    )


# ------------------------------------------------------------------ figures


def find_figures(page: M.PageImage, words: list[Word], rules: list[M.Rule], tables: list[Grid]) -> list[tuple[int, int, int, int]]:
    """Large areas of ink that are not text, table or a separator line."""
    cell = 16
    ink = page.ink.copy()
    pad = 6
    for w in words:
        ink[max(0, int(w.y0) - pad) : int(w.y1) + pad, max(0, int(w.x0) - pad) : int(w.x1) + pad] = False
    for g in tables:
        ink[max(0, int(g.y0) - pad) : int(g.y1) + pad, max(0, int(g.x0) - pad) : int(g.x1) + pad] = False
    for r in rules:
        # Long lone separators (e.g. above footnotes) are not pictures; frames are kept.
        if r.horizontal and (r.x1 - r.x0) > 0.45 * ink.shape[1]:
            ink[max(0, r.y0 - 3) : r.y1 + 3, max(0, r.x0 - 3) : r.x1 + 3] = False
    h, w = ink.shape
    gh, gw = h // cell, w // cell
    small = ink[: gh * cell, : gw * cell].reshape(gh, cell, gw, cell).mean(axis=(1, 3)) > 0.02
    # Close small gaps so one picture is one component.
    grown = small.copy()
    grown[1:, :] |= small[:-1, :]
    grown[:-1, :] |= small[1:, :]
    grown[:, 1:] |= small[:, :-1]
    grown[:, :-1] |= small[:, 1:]
    comps = [(x0 * cell, y0 * cell, min(x1 * cell, w), min(y1 * cell, h)) for x0, y0, x1, y1 in M.ink_components(grown, min_cells=12)]
    comps = _merge_boxes(comps, gap=int(0.03 * w))
    return [b for b in comps if (b[2] - b[0]) >= 0.08 * w and (b[3] - b[1]) >= 0.05 * h]


def _merge_boxes(boxes: list[tuple[int, int, int, int]], gap: int) -> list[tuple[int, int, int, int]]:
    boxes = list(boxes)
    changed = True
    while changed:
        changed = False
        out: list[tuple[int, int, int, int]] = []
        for b in boxes:
            for i, o in enumerate(out):
                if b[0] <= o[2] + gap and o[0] <= b[2] + gap and b[1] <= o[3] + gap and o[1] <= b[3] + gap:
                    out[i] = (min(b[0], o[0]), min(b[1], o[1]), max(b[2], o[2]), max(b[3], o[3]))
                    changed = True
                    break
            else:
                out.append(b)
        boxes = out
    return boxes


# ------------------------------------------------------------------ reading order


def xy_cut(lines: list[Line], rtl_page: bool, em: float) -> list[list[Line]]:
    """Order lines into reading columns with a recursive XY-cut.

    At each step, if a clear vertical gutter runs through every line, split
    into side-by-side columns (read right-to-left on Hebrew pages); otherwise
    split at the widest horizontal gap. Stacked pieces that are not
    side-by-side are joined back into one column afterwards.
    """
    columns, _ = _xy(lines, rtl_page, em)
    return columns


def _xy(lines: list[Line], rtl_page: bool, em: float) -> tuple[list[list[Line]], bool]:
    """Returns (columns, single) where single says the result is one column."""
    if len(lines) <= 1:
        return [list(lines)], True
    xs = _gaps(lines, "x")
    wide = [g for g in xs if g[1] - g[0] >= 1.2 * em]
    if wide:
        groups = _split_at(lines, "x", [max(wide, key=lambda g: g[1] - g[0])])
        groups.sort(key=lambda grp: -min(ln.x0 for ln in grp) if rtl_page else min(ln.x0 for ln in grp))
        cols: list[list[Line]] = []
        for grp in groups:
            sub, _ = _xy(grp, rtl_page, em)
            cols.extend(sub)
        return cols, False
    ys = [g for g in _gaps(lines, "y") if g[1] - g[0] > 0.05 * em]
    if not ys:
        return [sorted(lines, key=lambda ln: ln.y0)], True
    top, bottom = _split_at(lines, "y", [max(ys, key=lambda g: g[1] - g[0])])
    out: list[list[Line]] = []
    single_all = True
    for part in (top, bottom):
        sub, single = _xy(part, rtl_page, em)
        if single and out and out_single_last[0]:
            out[-1].extend(sub[0])
        else:
            out.extend(sub)
        out_single_last = [single]
        single_all = single_all and single
    for col in out:
        col.sort(key=lambda ln: ln.y0)
    return out, single_all and len(out) == 1


def _gaps(lines: list[Line], axis: str) -> list[tuple[float, float]]:
    spans = sorted((ln.x0, ln.x1) if axis == "x" else (ln.y0, ln.y1) for ln in lines)
    gaps = []
    reach = spans[0][1]
    for a, b in spans[1:]:
        if a > reach:
            gaps.append((reach, a))
        reach = max(reach, b)
    return gaps


def _split_at(lines: list[Line], axis: str, gaps: list[tuple[float, float]]) -> list[list[Line]]:
    cut = (gaps[0][0] + gaps[0][1]) / 2
    if axis == "x":
        left = [ln for ln in lines if ln.cx < cut]
        right = [ln for ln in lines if ln.cx >= cut]
        return [grp for grp in (left, right) if grp]
    above = [ln for ln in lines if (ln.y0 + ln.y1) / 2 < cut]
    below = [ln for ln in lines if (ln.y0 + ln.y1) / 2 >= cut]
    return [above, below]


# ------------------------------------------------------------------ paragraphs

LIST_MARKER = re.compile(
    r"^(?:[•●▪◦‣∙·■□➢►✓*\-–—]|\(?\d{1,3}[.)]|\(?[a-zA-Z][.)]|\(?[ivxlcIVXLC]{1,5}[.)]|\(?[א-ת]{1,2}[.)'׳])$"
)
CAPTION_START = re.compile(r"^(?:figure|fig\.|table|chart|plate|illustration|איור|טבלה|תמונה|תרשים)\s*[\dא-ת]", re.I)
PAGE_NUMBER = re.compile(r"^(?:[-–—]\s*)?(?:page\s+)?\d{1,4}(?:\s*[-–—])?$|^(?:עמוד\s+)?\d{1,4}$|^[א-ת]{1,3}['׳\"״]?$", re.I)


_BULLET_LOOKALIKES = set("eoO0©®°«»*.-–·•●▪■")


def line_marker(line: Line) -> str:
    """The list marker that starts this line, or "" if it does not start with one.

    Besides the usual bullets and numbers, a tiny blob followed by a wide gap
    is a bullet that the OCR misread (Tesseract often reads "•" as "e" or ".").
    """
    if len(line.words) < 2:
        return ""
    first, second = line.words[0], line.words[1]
    if LIST_MARKER.match(first.text):
        return first.text
    gap = (first.x0 - second.x1) if line.rtl else (second.x0 - first.x1)
    em = line.em or first.h
    if len(first.text) <= 2 and set(first.text) <= _BULLET_LOOKALIKES and first.w <= 0.6 * em and gap >= 0.8 * em:
        return "•"
    return ""


def _normal_pitch(col: list[Line]) -> float:
    """Baseline-to-baseline distance (in ems) of lines inside one paragraph.

    The smallest pitch between neighbouring lines of the same size is the
    ordinary line spacing; anything clearly larger is a paragraph gap.
    """
    pitches = []
    for a, b in zip(col, col[1:]):
        if abs(a.em - b.em) / max(a.em, b.em) < 0.1 and b.y0 > a.y0:
            pitches.append((b.baseline - a.baseline) / ((a.em + b.em) / 2))
    pitches = [p for p in pitches if p >= 0.9]
    if not pitches:
        return 1.3
    return min(min(pitches), 2.2)


def paragraphs(col: list[Line], col_x0: float, col_x1: float) -> list[list[Line]]:
    if not col:
        return []
    pitch = _normal_pitch(col)
    width = max(col_x1 - col_x0, 1)
    paras: list[list[Line]] = [[col[0]]]
    for prev, cur in zip(col, col[1:]):
        em = max(prev.em, cur.em)
        rtl = cur.rtl
        start_edge = col_x1 if rtl else col_x0
        cur_indent = abs(cur.start - start_edge)
        prev_indent = abs(prev.start - start_edge)
        prev_fill = prev.width / width
        brk = False
        if (cur.baseline - prev.baseline) / ((prev.em + cur.em) / 2) > pitch + 0.3:
            brk = True
        elif abs(prev.em - cur.em) / em > 0.14:
            brk = True
        elif (prev.bold_frac > 0.8) != (cur.bold_frac > 0.8) and max(prev.bold_frac, cur.bold_frac) > 0.8:
            brk = True
        elif line_marker(cur):
            brk = True
        elif cur_indent > prev_indent + 1.0 * em and prev_fill < 0.98:
            brk = True
        elif prev_fill < 0.7 and ends_sentence(prev.text) and abs(prev.cx - cur.cx) > 0.1 * width:
            brk = True
        if brk:
            paras.append([cur])
        else:
            paras[-1].append(cur)
    return paras


def detect_alignment(lines: list[Line], col_x0: float, col_x1: float, page_cx: Optional[float] = None) -> str:
    width = max(col_x1 - col_x0, 1)
    em = statistics.median([ln.em for ln in lines]) or 10
    tol = max(0.6 * em, 0.012 * width)
    rtl = lines[0].rtl
    if len(lines) == 1:
        ln = lines[0]
        col_cx = (col_x0 + col_x1) / 2
        near = max(0.03 * width, em)
        centred = abs(ln.cx - col_cx) < near or (page_cx is not None and abs(ln.cx - page_cx) < near)
        if ln.width < 0.92 * width and centred:
            return "center"
        if ln.width >= 0.97 * width:
            return "justify"
        if abs(ln.x1 - col_x1) < tol and abs(ln.x0 - col_x0) > tol:
            return "right"
        return "right" if rtl and abs(ln.x1 - col_x1) < 3 * tol else "left"
    body = lines[:-1]
    lefts = [ln.x0 for ln in body]
    rights = [ln.x1 for ln in body]
    left_even = max(lefts) - min(lefts) < tol
    right_even = max(rights) - min(rights) < tol
    centers = [ln.cx for ln in lines]
    if left_even and right_even:
        return "justify"
    if max(centers) - min(centers) < tol and not left_even and not right_even:
        return "center"
    if right_even and not left_even:
        return "right"
    if left_even and not right_even:
        return "left"
    return "right" if rtl else "left"


# ------------------------------------------------------------------ runs


def words_to_runs(words: list[Word]) -> list[Run]:
    runs: list[Run] = []
    for i, w in enumerate(words):
        if i:
            space_fmt = dict(
                bold=w.bold and words[i - 1].bold,
                italic=w.italic and words[i - 1].italic,
                underline=w.underline and words[i - 1].underline,
                color=w.color if similar_color(w.color, words[i - 1].color) else None,
            )
            runs.append(Run(text=" ", **{k: bool(v) if k != "color" else v for k, v in space_fmt.items()}))
        uncertain = w.conf is not None and 0 <= w.conf < UNCERTAIN_CONF
        runs.append(
            Run(
                text=w.text,
                bold=bool(w.bold),
                italic=bool(w.italic),
                underline=w.underline,
                strike=w.strike,
                superscript=w.superscript,
                subscript=w.subscript,
                color=w.color,
                uncertain=uncertain,
                confidence=None if w.conf is None or w.conf < 0 else round(w.conf, 1),
            )
        )
    return runs


def _same_format(a: Run, b: Run) -> bool:
    return (a.bold, a.italic, a.underline, a.strike, a.superscript, a.subscript, a.uncertain) == (
        b.bold,
        b.italic,
        b.underline,
        b.strike,
        b.superscript,
        b.subscript,
        b.uncertain,
    ) and similar_color(a.color, b.color)


def merge_runs(runs: list[Run]) -> list[Run]:
    out: list[Run] = []
    for r in runs:
        if not r.text:
            continue
        if out and _same_format(out[-1], r):
            prev = out[-1]
            conf = [c for c in (prev.confidence, r.confidence) if c is not None]
            prev.text += r.text
            prev.confidence = min(conf) if conf else None
        elif out and r.text == " ":
            out[-1].text += " "
        else:
            out.append(r.model_copy())
    return out


def lines_to_runs(lines: list[Line]) -> list[Run]:
    runs: list[Run] = []
    for i, ln in enumerate(lines):
        line_runs = words_to_runs(ln.words)
        if i and runs and line_runs:
            prev_text = runs[-1].text
            first = line_runs[0]
            joined = dehyphenate_join(prev_text, first.text)
            if joined == prev_text.rstrip()[:-1] + first.text.lstrip():
                runs[-1].text = prev_text.rstrip()[:-1]
            else:
                runs.append(Run(text=" ", bold=runs[-1].bold and first.bold, italic=runs[-1].italic and first.italic))
        runs.extend(line_runs)
    return merge_runs(runs)


# ------------------------------------------------------------------ main entry


@dataclass
class LayoutResult:
    blocks: list[Block]
    regions: list[Region] = field(default_factory=list)
    quality: Optional[float] = None
    figure_boxes: list[tuple[int, int, int, int]] = field(default_factory=list)


def analyze(
    words: list[Word],
    page: Optional[M.PageImage],
    dpi: int,
    width_px: int,
    height_px: int,
) -> LayoutResult:
    measure_words(words, page, dpi)
    _fill_missing_em(words)
    _decide_scripts(words)
    first_pass = build_lines(words)
    decide_emphasis(first_pass)
    for ln in first_pass:
        smooth_line_emphasis(ln)

    rules = M.find_rules(page) if page is not None else []
    grids = find_tables(rules)
    VERTICAL_RULES[:] = [r for r in rules if not r.horizontal and not any(g.x0 - 5 <= r.x0 <= g.x1 + 5 and g.y0 - 5 <= r.y0 <= g.y1 + 5 for g in grids)]
    rtl_chars = sum(len(w.text) for w in words if w.rtl)
    ltr_chars = sum(len(w.text) for w in words if not w.rtl)
    rtl_page = rtl_chars > ltr_chars

    table_words: dict[int, list[Word]] = {i: [] for i in range(len(grids))}
    flow_words: list[Word] = []
    for w in words:
        for i, g in enumerate(grids):
            if g.x0 - 4 <= w.cx <= g.x1 + 4 and g.y0 - 4 <= (w.y0 + w.y1) / 2 <= g.y1 + 4:
                table_words[i].append(w)
                break
        else:
            flow_words.append(w)

    lines = build_lines(flow_words)
    _mark_super_sub(lines)
    for ln in lines:
        ln.finish()
    page_em = statistics.median([ln.em for ln in lines]) if lines else 40.0

    blocks: list[tuple[float, Block]] = []
    for i, g in enumerate(grids):
        blk = table_block(g, table_words[i], rtl_page, width_px, height_px)
        blk.font_size = _size_pt(statistics.median([w.em for w in table_words[i]]), dpi) if table_words[i] else None
        blocks.append((g.y0, blk))

    figure_boxes = find_figures(page, words, rules, grids) if page is not None else []
    for box in figure_boxes:
        x0, y0, x1, y1 = box
        blk = Block(
            type="figure",
            figure=Figure(image="", width_frac=round((x1 - x0) / max(width_px * 0.75, 1), 3)),
            bbox=(x0 / width_px, y0 / height_px, x1 / width_px, y1 / height_px),
            align="center",
        )
        blocks.append((y0, blk))

    columns = xy_cut(lines, rtl_page, page_em)
    regions, col_labels = _regions_from_columns(columns)
    text_blocks: list[Block] = []
    all_x0 = min((ln.x0 for ln in lines), default=0)
    all_x1 = max((ln.x1 for ln in lines), default=width_px)
    beside = _side_by_side(columns)
    for k, col in enumerate(columns):
        col_x0 = min(ln.x0 for ln in col)
        col_x1 = max(ln.x1 for ln in col)
        if k not in beside:
            # Measure alignment against the page's text area, not the block itself.
            col_x0, col_x1 = min(col_x0, all_x0), max(col_x1, all_x1)
        for para in paragraphs(col, col_x0, col_x1):
            blk = _make_block(para, col_x0, col_x1, dpi, width_px, height_px, None if k in beside else width_px / 2)
            if regions:
                blk.region = col_labels.get(k, "main")
            text_blocks.append(blk)

    # Tables and figures slot in by vertical position.
    all_blocks = _interleave(text_blocks, blocks, height_px)
    _classify(all_blocks, height_px)
    confs = [w.conf for w in words if w.conf is not None and w.conf >= 0]
    weights = [len(w.text) for w in words if w.conf is not None and w.conf >= 0]
    quality = float(np.average(confs, weights=weights)) if confs else None
    return LayoutResult(blocks=all_blocks, regions=regions, quality=quality, figure_boxes=figure_boxes)


def _decide_scripts(words: list[Word]) -> None:
    for w in words:
        if w.font_category is None:
            w.font_category = "serif"


def _mark_super_sub(lines: list[Line]) -> None:
    for ln in lines:
        if len(ln.words) < 3:
            continue
        bottoms = sorted(w.y1 for w in ln.words if not any(c in _LATIN_DESC | _HEB_DESC for c in w.text))
        if not bottoms:
            continue
        baseline = statistics.median(bottoms)
        em = ln.em
        for w in ln.words:
            small = w.em and w.em < 0.75 * em or w.h < 0.45 * em
            if not small:
                continue
            if w.y1 < baseline - 0.25 * em:
                w.superscript = True
            elif w.y0 > baseline - 0.3 * em and w.y1 > baseline + 0.08 * em:
                w.subscript = True


def _size_pt(em_px: float, dpi: int) -> float:
    return round(em_px * 72.0 / dpi * 2) / 2


def _make_block(
    para: list[Line], col_x0: float, col_x1: float, dpi: int, width_px: int, height_px: int, page_cx: Optional[float] = None
) -> Block:
    rtl_n = sum(sum(len(w.text) for w in ln.words if w.rtl) for ln in para)
    ltr_n = sum(sum(len(w.text) for w in ln.words if not w.rtl) for ln in para)
    rtl = rtl_n > ltr_n
    for ln in para:
        ln.rtl = rtl
    words = [w for ln in para for w in ln.words]
    ems = [w.em * len(w.text) for w in words if w.em]
    em = sum(ems) / max(sum(len(w.text) for w in words if w.em), 1) if ems else para[0].em
    x0 = min(ln.x0 for ln in para)
    x1 = max(ln.x1 for ln in para)
    y0 = min(ln.y0 for ln in para)
    y1 = max(ln.y1 for ln in para)
    align = detect_alignment(para, col_x0, col_x1, page_cx)
    start_edge = col_x1 if rtl else col_x0
    body_lines = para[1:] if len(para) > 1 else para
    body_start = statistics.median([abs(ln.start - start_edge) for ln in body_lines])
    first_start = abs(para[0].start - start_edge)
    px_to_pt = 72.0 / dpi
    indent = 0.0 if align in ("center",) else round(body_start * px_to_pt, 1)
    first = round((first_start - body_start) * px_to_pt, 1) if len(para) > 1 and align != "center" else 0.0
    runs = lines_to_runs(para)
    marker = line_marker(para[0])
    if marker:
        runs = lines_to_runs([Line(para[0].words[1:], rtl=rtl).finish()] + para[1:])
    cats = [w.font_category for w in words if w.font_category]
    blk = Block(
        type="list_item" if marker else "paragraph",
        list_marker=marker,
        align=align,
        direction="rtl" if rtl else "ltr",
        indent=max(indent, 0.0),
        first_line_indent=first if abs(first) >= 6 else 0.0,
        font_size=_size_pt(em, dpi),
        font_category=max(set(cats), key=cats.count) if cats else "serif",
        runs=runs,
        bbox=(x0 / width_px, y0 / height_px, x1 / width_px, y1 / height_px),
    )
    return blk


def _interleave(text_blocks: list[Block], others: list[tuple[float, Block]], height_px: int) -> list[Block]:
    out = list(text_blocks)
    for y, blk in sorted(others, key=lambda t: t[0]):
        pos = len(out)
        for i, tb in enumerate(out):
            if tb.bbox and tb.bbox[1] * height_px > y and tb.type != "figure":
                pos = i
                break
        out.insert(pos, blk)
    return out


def _side_by_side(columns: list[list[Line]]) -> set[int]:
    boxes = [(min(ln.x0 for ln in c), min(ln.y0 for ln in c), max(ln.x1 for ln in c), max(ln.y1 for ln in c)) for c in columns]
    out = set()
    for i, a in enumerate(boxes):
        for j, b in enumerate(boxes):
            if i != j and min(a[3], b[3]) > max(a[1], b[1]) and (a[2] < b[0] or b[2] < a[0]):
                out.add(i)
    return out


def _regions_from_columns(columns: list[list[Line]]) -> tuple[list[Region], dict[int, str]]:
    """Side-by-side columns with clearly different type sizes are separate texts
    (e.g. main text and commentary), not one text flowing across columns.
    Returns the regions and a map from column index to region id."""
    if len(columns) < 2:
        return [], {}
    info = []
    for col in columns:
        info.append(
            (
                min(ln.x0 for ln in col),
                min(ln.y0 for ln in col),
                max(ln.x1 for ln in col),
                max(ln.y1 for ln in col),
                statistics.median([ln.em for ln in col]),
                sum(len(ln.text) for ln in col),
            )
        )
    pairs = []
    for i, a in enumerate(info):
        for j, b in enumerate(info):
            overlap_y = min(a[3], b[3]) - max(a[1], b[1])
            apart_x = a[2] < b[0] or b[2] < a[0]
            if i < j and overlap_y > 0 and apart_x:
                pairs.append((i, j))
    if not pairs:
        return [], {}
    if not any(abs(info[i][4] - info[j][4]) / max(info[i][4], info[j][4]) > 0.15 for i, j in pairs):
        return [], {}
    involved = sorted({k for pair in pairs for k in pair})
    # The main text is the column with the most (and largest) type.
    main = max(involved, key=lambda k: info[k][4] * info[k][5])
    regions = [Region(id="main", label="Main text", kind="main", order=0)]
    labels = {}
    n = 0
    for k in involved:
        if k == main:
            continue
        n += 1
        rid = f"commentary{n}"
        regions.append(Region(id=rid, label=f"Commentary {n}", kind="commentary", order=n))
        labels[k] = rid
    return regions, labels


def _classify(blocks: list[Block], height_px: int) -> None:
    """Decide headings, captions, footnotes, quotes and running headers/footers."""
    text = [b for b in blocks if b.type in ("paragraph", "list_item")]
    if not text:
        return
    sizes = []
    for b in text:
        n = len(b.text)
        sizes += [b.font_size or 0] * max(n // 20, 1)
    body = statistics.median([s for s in sizes if s]) if any(sizes) else 12.0
    for i, b in enumerate(blocks):
        if b.type not in ("paragraph", "list_item"):
            continue
        t = b.text.strip()
        nchars = len(t)
        top = b.bbox[1] if b.bbox else 0.5
        bottom = b.bbox[3] if b.bbox else 0.5
        size = b.font_size or body
        all_bold = bool(b.runs) and all(r.bold for r in b.runs if r.text.strip())
        prev_blk = blocks[i - 1] if i else None
        next_blk = blocks[i + 1] if i + 1 < len(blocks) else None
        if bottom < 0.075 and size <= body * 1.05 and nchars < 120:
            b.type = "page_number" if PAGE_NUMBER.match(t) else "header"
        elif top > 0.92 and size <= body * 1.05 and nchars < 120:
            b.type = "page_number" if PAGE_NUMBER.match(t) else "footer"
        elif b.type == "list_item":
            continue
        elif CAPTION_START.match(t) or (
            nchars < 160
            and size < body * 0.95
            and ((prev_blk is not None and prev_blk.type in ("figure", "table")) or (next_blk is not None and next_blk.type in ("figure", "table")))
        ):
            b.type = "caption"
        elif top > 0.72 and size < body * 0.88 and re.match(r"^[\d*†‡]", t):
            b.type = "footnote"
        elif (size >= body * 1.18 and nchars < 200) or (all_bold and nchars < 90 and not ends_sentence(t)):
            b.type = "heading"
            b.level = 0  # decided across the whole document by the normaliser
        elif b.indent >= 24 and b.align != "center" and size <= body * 1.05 and _both_sides_indented(b, blocks):
            b.type = "quote"


def _both_sides_indented(b: Block, blocks: list[Block]) -> bool:
    peers = [x for x in blocks if x.type == "paragraph" and x is not b and x.bbox]
    if not peers or not b.bbox:
        return False
    left = min(x.bbox[0] for x in peers)
    right = max(x.bbox[2] for x in peers)
    return b.bbox[0] - left > 0.03 and right - b.bbox[2] > 0.03
