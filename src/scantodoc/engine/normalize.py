"""Whole-document clean-up after the pages have been read.

* Headings of the same kind get the same level everywhere.
* Every element type gets one document-wide "detected" style (size, font
  category, bold, colour, alignment), so exports are consistent.
* Running headers, footers and page numbers are recognised by repetition.
* Paragraphs split across a page break are marked so exports can join them.
* Near-identical colours (scanner noise) are snapped to one value.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from difflib import SequenceMatcher

from ..model import DetectedStyle, Document, element_key
from ..text import ends_sentence
from .layout import PAGE_NUMBER, similar_color

BODY_TYPES = ("paragraph", "list_item", "quote")


def normalize(doc: Document) -> Document:
    pages = [p for p in doc.pages if p.status == "done"]
    _snap_colors(doc)
    _running_heads(pages)
    _heading_levels(doc)
    _continuations(pages)
    doc.detected = _detected_styles(doc)
    rtl = ltr = 0
    for _, b in doc.iter_blocks():
        n = len(b.text)
        if b.direction == "rtl":
            rtl += n
        else:
            ltr += n
    doc.main_direction = "rtl" if rtl > ltr else "ltr"
    doc.touch()
    return doc


def _snap_colors(doc: Document) -> None:
    centres: list[str] = []
    for _, b in doc.iter_blocks():
        runs = list(b.runs)
        if b.table:
            for row in b.table.rows:
                for c in row:
                    runs.extend(c.runs)
        for r in runs:
            if not r.color:
                continue
            for c in centres:
                if similar_color(c, r.color, tol=45):
                    r.color = c
                    break
            else:
                centres.append(r.color)


def _norm_text(t: str) -> str:
    return re.sub(r"\d+", "#", re.sub(r"\s+", " ", t.strip().lower()))


def _running_heads(pages) -> None:
    """Text repeated at the top (or bottom) of several pages is a running head."""
    if len(pages) < 2:
        return
    for zone, kind in (("top", "header"), ("bottom", "footer")):
        candidates = []
        for p in pages:
            for b in p.blocks:
                if not b.bbox or b.type in ("table", "figure") or b.user_edited:
                    continue
                if (zone == "top" and b.bbox[3] < 0.12) or (zone == "bottom" and b.bbox[1] > 0.88):
                    candidates.append((p.index, b))
        for idx, b in candidates:
            t = _norm_text(b.text)
            if not t:
                continue
            if PAGE_NUMBER.match(b.text.strip()):
                b.type = "page_number"
                continue
            repeats = sum(
                1
                for j, other in candidates
                if j != idx and SequenceMatcher(None, t, _norm_text(other.text)).ratio() > 0.8
            )
            if repeats >= 1 and len(t) < 150:
                b.type = kind


def _heading_levels(doc: Document) -> None:
    heads = [b for _, b in doc.iter_blocks() if b.type == "heading"]
    if not heads:
        return
    undecided = [b for b in heads if b.level == 0]
    decided = [b for b in heads if b.level > 0 and not b.user_edited]
    if undecided:
        # Group sizes into clusters (within ~8%); bigger clusters rank higher.
        sizes = sorted({round(b.font_size or 0, 1) for b in undecided}, reverse=True)
        clusters: list[list[float]] = []
        for s in sizes:
            if clusters and abs(clusters[-1][-1] - s) <= max(0.08 * s, 0.6):
                clusters[-1].append(s)
            else:
                clusters.append([s])
        level_of = {}
        for rank, cl in enumerate(clusters):
            for s in cl:
                level_of[s] = min(rank + 1, 4)
        for b in undecided:
            b.level = level_of.get(round(b.font_size or 0, 1), 1)
    if decided:
        # Claude decides levels page by page; make headings of one size share a level.
        by_size: dict[float, Counter] = {}
        for b in decided:
            if b.font_size:
                by_size.setdefault(round(b.font_size), Counter())[b.level] += 1
        for b in decided:
            if b.font_size and round(b.font_size) in by_size:
                b.level = by_size[round(b.font_size)].most_common(1)[0][0]


def _continuations(pages) -> None:
    for prev, nxt in zip(pages, pages[1:]):
        last = next((b for b in reversed(prev.blocks) if b.type in BODY_TYPES and not b.region), None)
        first = next((b for b in nxt.blocks if b.type in BODY_TYPES and not b.region), None)
        if not last or not first or last.type != first.type:
            continue
        if last.continues or first.continued:
            last.continues = first.continued = True
            continue
        if prev.reader == "claude" and nxt.reader == "claude":
            continue  # Claude already told us
        t1 = last.text.rstrip()
        t2 = first.text.lstrip()
        starts_lower = bool(t2[:1]) and t2[:1].islower()
        if t1 and t2 and not ends_sentence(t1) and (starts_lower or first.direction == "rtl") and first.first_line_indent <= 0:
            last.continues = first.continued = True


def _detected_styles(doc: Document) -> dict[str, DetectedStyle]:
    groups: dict[str, list] = {}
    for _, b in doc.iter_blocks():
        if b.type in ("figure", "page_number"):
            continue
        groups.setdefault(element_key(b), []).append(b)
    out: dict[str, DetectedStyle] = {}
    for key, blocks in groups.items():
        weighted_sizes = []
        cats: Counter = Counter()
        aligns: Counter = Counter()
        colors: Counter = Counter()
        bold_chars = italic_chars = total = 0
        for b in blocks:
            n = max(len(b.text), 1)
            if b.font_size:
                weighted_sizes += [b.font_size] * max(n // 10, 1)
            cats[b.font_category] += n
            aligns[b.align] += n
            runs = b.runs
            if b.table:
                runs = [r for row in b.table.rows for c in row for r in c.runs]
            for r in runs:
                k = len(r.text.strip())
                total += k
                bold_chars += k if r.bold else 0
                italic_chars += k if r.italic else 0
                colors[r.color or ""] += k
        out[key] = DetectedStyle(
            font_size=round(statistics.median(weighted_sizes) * 2) / 2 if weighted_sizes else None,
            font_category=cats.most_common(1)[0][0] if cats else "serif",
            bold=total > 0 and bold_chars / total > 0.6,
            italic=total > 0 and italic_chars / total > 0.6,
            color=(colors.most_common(1)[0][0] or None) if colors else None,
            align=aligns.most_common(1)[0][0] if aligns else None,
        )
    return out
