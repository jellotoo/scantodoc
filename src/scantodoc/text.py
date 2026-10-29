"""Text helpers shared by readers and exporters: script detection, bidi
segmentation, nikud stripping. Text is always stored in logical (reading)
order; nothing here ever reverses characters for display."""

from __future__ import annotations

import re
import unicodedata

HEBREW_RANGES = ((0x0590, 0x05FF), (0xFB1D, 0xFB4F))
_NIKUD = set(range(0x05B0, 0x05BE)) | {0x05BF, 0x05C1, 0x05C2, 0x05C4, 0x05C5, 0x05C7}
_TEAMIM = set(range(0x0591, 0x05B0))
FINAL_LETTERS = set("ךםןףץ")
SENTENCE_END = tuple(".!?:;׃\"'”’»)]")


def is_hebrew(ch: str) -> bool:
    o = ord(ch)
    return any(a <= o <= b for a, b in HEBREW_RANGES)


def char_class(ch: str) -> str:
    """'R' for right-to-left letters, 'L' for left-to-right letters, 'N' otherwise."""
    bidi = unicodedata.bidirectional(ch)
    if bidi in ("R", "AL"):
        return "R"
    if bidi == "L":
        return "L"
    return "N"


def count_strong(text: str) -> tuple[int, int]:
    rtl = ltr = 0
    for ch in text:
        c = char_class(ch)
        if c == "R":
            rtl += 1
        elif c == "L":
            ltr += 1
    return rtl, ltr


def has_rtl(text: str) -> bool:
    return any(char_class(ch) == "R" for ch in text)


def detect_direction(text: str, default: str = "ltr") -> str:
    rtl, ltr = count_strong(text)
    if rtl == ltr == 0:
        return default
    return "rtl" if rtl >= ltr else "ltr"


def split_by_direction(text: str, base: str = "ltr") -> list[tuple[str, str]]:
    """Split text into (segment, "rtl"|"ltr") pieces by script.

    Neutral characters (spaces, punctuation, digits) between two letters of the
    same direction join that direction; neutrals between different directions,
    or at either end, take the paragraph's base direction. This mirrors how
    Word assigns runs when someone types mixed Hebrew/English text.
    """
    if not text:
        return []
    classes = [char_class(ch) for ch in text]
    n = len(text)
    resolved = list(classes)
    i = 0
    while i < n:
        if classes[i] != "N":
            i += 1
            continue
        j = i
        while j < n and classes[j] == "N":
            j += 1
        before = classes[i - 1] if i > 0 else None
        after = classes[j] if j < n else None
        base_cls = "R" if base == "rtl" else "L"
        if before and after and before == after:
            fill = before
        else:
            fill = base_cls
        for k in range(i, j):
            resolved[k] = fill
        if before == "L" and fill != "L":
            # Numbers right after Latin text belong to it ("Chapter 12" stays in
            # that order inside a Hebrew paragraph), as in the Unicode bidi rules.
            last_digit = max((k for k in range(i, j) if text[k].isdigit()), default=-1)
            if last_digit >= 0:
                for k in range(i, last_digit + 1):
                    resolved[k] = "L"
        i = j
    out: list[tuple[str, str]] = []
    start = 0
    for k in range(1, n + 1):
        if k == n or resolved[k] != resolved[start]:
            out.append((text[start:k], "rtl" if resolved[start] == "R" else "ltr"))
            start = k
    return out


def strip_marks(text: str, nikud: bool = True, teamim: bool = True) -> str:
    drop = (_NIKUD if nikud else set()) | (_TEAMIM if teamim else set())
    if not drop:
        return text
    return "".join(ch for ch in text if ord(ch) not in drop)


def base_letters(text: str) -> str:
    """Text without nikud/ta'amim and with collapsed whitespace, for comparisons."""
    return re.sub(r"\s+", " ", strip_marks(text)).strip()


def looks_visual_order(text: str) -> bool:
    """True if Hebrew words seem stored backwards (visual order), which some
    older PDF producers do. Final letters (ך ם ן ף ץ) belong at the END of a
    word in logical order; finding them mostly at the start means reversed."""
    at_start = at_end = 0
    for word in re.findall(r"[א-ת]{2,}", text):
        if word[0] in FINAL_LETTERS:
            at_start += 1
        if word[-1] in FINAL_LETTERS:
            at_end += 1
    return at_start >= 3 and at_start > 2 * at_end


def reverse_visual_line(text: str) -> str:
    """Turn one visually-ordered line into logical order: reverse the line,
    then flip back any left-to-right pieces (numbers, Latin words)."""
    rev = text[::-1]
    return re.sub(r"[A-Za-z0-9][A-Za-z0-9.,:/\-]*[A-Za-z0-9]|[A-Za-z0-9]", lambda m: m.group(0)[::-1], rev)


def ends_sentence(text: str) -> bool:
    t = text.rstrip()
    return bool(t) and t.endswith(SENTENCE_END)


def dehyphenate_join(a: str, b: str) -> str:
    """Join two pieces of a paragraph split across lines or pages."""
    a_stripped = a.rstrip()
    b_stripped = b.lstrip()
    if re.search(r"[A-Za-z]-$", a_stripped) and b_stripped[:1].islower():
        return a_stripped[:-1] + b_stripped
    if re.search(r"[\u05D0-\u05EA][-\u05BE]$", a_stripped):
        return a_stripped + b_stripped  # Hebrew prefix letter + maqaf, e.g. "ו-Rambam"
    if not a_stripped:
        return b_stripped
    return a_stripped + " " + b_stripped
