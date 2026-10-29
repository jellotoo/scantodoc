"""Styling options, applied when exporting (never baked into the document model).

Every option defaults to "keep what was detected", so an export with no
options looks like the original page.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from ..model import ELEMENT_KEYS

HEX = r"^#[0-9A-Fa-f]{6}$"


def _hex(v: Optional[str]) -> Optional[str]:
    if v in (None, "", "keep", "auto"):
        return None
    v = v.strip()
    if not v.startswith("#"):
        v = "#" + v
    if len(v) == 4:  # #abc -> #aabbcc
        v = "#" + "".join(c * 2 for c in v[1:])
    if len(v) != 7 or any(c not in "0123456789abcdefABCDEF" for c in v[1:]):
        raise ValueError(f"not a colour: {v!r} (use #RRGGBB)")
    return v.upper()


class FontPair(BaseModel):
    """A font for Latin-script text and a font for Hebrew-script text."""

    latin: Optional[str] = None  # None = keep detected
    hebrew: Optional[str] = None

    def merged(self, fallback: "FontPair") -> "FontPair":
        return FontPair(latin=self.latin or fallback.latin, hebrew=self.hebrew or fallback.hebrew)


class Fonts(BaseModel):
    body: FontPair = Field(default_factory=FontPair)  # applies to everything not overridden
    headings: FontPair = Field(default_factory=FontPair)  # all heading levels
    elements: dict[str, FontPair] = Field(default_factory=dict)  # h1..h4, list, table, caption, footnote, quote


class Sizes(BaseModel):
    mode: Literal["keep", "exact", "scale"] = "keep"
    scale: float = 100.0  # percent, used in "scale" mode
    exact: dict[str, float] = Field(default_factory=dict)  # element -> points, used in "exact" mode


class Colors(BaseModel):
    mode: Literal["keep", "black", "custom"] = "keep"
    custom: dict[str, str] = Field(default_factory=dict)  # element (body, h1..h4, list, quote...) -> #RRGGBB
    link: Optional[str] = None
    page_background: Optional[str] = None
    accent: Optional[str] = None  # colour of the line under/beside headings
    accent_style: Literal["none", "underline", "rule", "bar"] = "none"

    @field_validator("link", "page_background", "accent", mode="before")
    @classmethod
    def _check(cls, v):
        return _hex(v)

    @field_validator("custom", mode="before")
    @classmethod
    def _check_custom(cls, v):
        return {k: _hex(c) for k, c in (v or {}).items() if _hex(c)}


class Emphasis(BaseModel):
    bold: bool = True  # keep detected bold (False strips it from the text)
    italic: bool = True
    underline: bool = True
    strike: bool = True
    bold_lines_to_headings: bool = False  # short all-bold lines become real headings
    bold_line_heading_level: int = 3


class Spacing(BaseModel):
    line_spacing: Optional[float] = None  # multiple of single spacing; None = automatic
    space_before: Optional[float] = None  # points before body paragraphs
    space_after: Optional[float] = None  # points after body paragraphs
    first_line_indent: Optional[float] = None  # points; None = keep detected


class Margins(BaseModel):
    top: float = 1.0
    bottom: float = 1.0
    left: float = 1.0
    right: float = 1.0


class PageSetup(BaseModel):
    size: Literal["keep", "letter", "a4", "legal", "a5", "custom"] = "keep"
    width_in: float = 8.5
    height_in: float = 11.0
    orientation: Literal["portrait", "landscape"] = "portrait"
    margins: Margins = Field(default_factory=Margins)
    columns: int = 1


class Alignment(BaseModel):
    mode: Literal["keep", "start", "left", "right", "justify"] = "keep"
    headings: bool = False  # also force the alignment of headings


class Extras(BaseModel):
    toc: bool = False
    toc_title: str = "Contents"
    page_numbers: bool = False
    page_number_align: Literal["center", "left", "right"] = "center"
    title_page: bool = False
    title: str = ""
    subtitle: str = ""
    author: str = ""
    keep_headers_footers: bool = False  # running heads printed on the scanned pages
    keep_page_numbers: bool = False  # the scan's own printed page numbers
    merge_across_pages: bool = True
    strip_nikud: bool = False
    strip_teamim: bool = False
    include_figures: bool = True
    regions: Literal["per_page", "grouped", "main_only"] = "per_page"
    link_urls: bool = True
    highlight_uncertain: bool = False  # mark words the reader was unsure of (for proofreading)


class StyleOptions(BaseModel):
    name: str = ""
    description: str = ""
    fonts: Fonts = Field(default_factory=Fonts)
    sizes: Sizes = Field(default_factory=Sizes)
    colors: Colors = Field(default_factory=Colors)
    emphasis: Emphasis = Field(default_factory=Emphasis)
    spacing: Spacing = Field(default_factory=Spacing)
    page: PageSetup = Field(default_factory=PageSetup)
    alignment: Alignment = Field(default_factory=Alignment)
    extras: Extras = Field(default_factory=Extras)

    def font_for(self, element: str) -> FontPair:
        """Font choice for an element: its own override, then headings, then body."""
        own = self.fonts.elements.get(element, FontPair())
        if element in ("h1", "h2", "h3", "h4"):
            own = own.merged(self.fonts.headings)
        return own.merged(self.fonts.body)


ELEMENTS = ELEMENT_KEYS


def set_path(obj: BaseModel, path: str, value: Any) -> BaseModel:
    """Set a nested option by dotted path, e.g. set_path(s, "colors.custom.h1", "#1F3A5F")."""
    data = obj.model_dump()
    cur: Any = data
    parts = path.split(".")
    for p in parts[:-1]:
        if p not in cur or cur[p] is None:
            cur[p] = {}
        cur = cur[p]
    if isinstance(value, str):
        low = value.lower()
        if low in ("true", "yes", "on"):
            value = True
        elif low in ("false", "no", "off"):
            value = False
        elif low in ("none", "null", "keep", ""):
            value = None
        else:
            try:
                value = float(value) if "." in value else int(value)
            except ValueError:
                pass
    cur[parts[-1]] = value
    return type(obj).model_validate(data)


def merge(base: StyleOptions, overlay: dict) -> StyleOptions:
    """Deep-merge a (partial) dict of options onto existing options."""

    def deep(a: dict, b: dict) -> dict:
        out = dict(a)
        for k, v in b.items():
            if isinstance(v, dict) and isinstance(out.get(k), dict):
                out[k] = deep(out[k], v)
            else:
                out[k] = v
        return out

    return StyleOptions.model_validate(deep(base.model_dump(), overlay))
