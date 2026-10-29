"""The Claude reader: send a page image to Claude and get back a structured
description of the page (blocks, runs, tables, regions) as strict JSON.

Structured outputs constrain Claude's reply to the JSON schema below; the
reply is then validated again with pydantic, and the request is retried once
with the validation error if anything is off.
"""

from __future__ import annotations

import base64
import io
import json
from typing import Any, Literal, Optional

from PIL import Image
from pydantic import BaseModel, ValidationError

from ... import config
from ...model import Block, Cell, Figure, Region, Run, Table, Usage
from .. import cost as costs
from .base import PageInput, PageResult, ReaderError

PROMPT_VERSION = "claude-page-3"
MAX_TOKENS = 64000

# ---------------------------------------------------------------- the JSON schema

BLOCK_TYPES = ["heading", "paragraph", "list_item", "table", "caption", "footnote", "header", "footer", "page_number", "quote", "figure"]
FONT_CATEGORIES = ["serif", "sans-serif", "monospace", "script", "rashi"]

RUN_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "bold": {"type": "boolean"},
        "italic": {"type": "boolean"},
        "underline": {"type": "boolean"},
        "strikethrough": {"type": "boolean"},
        "superscript": {"type": "boolean"},
        "subscript": {"type": "boolean"},
        "color": {"type": "string", "description": "#RRGGBB when clearly coloured, otherwise empty"},
        "uncertain": {"type": "boolean"},
    },
    "required": ["text", "bold", "italic", "underline", "strikethrough", "superscript", "subscript", "color", "uncertain"],
    "additionalProperties": False,
}

CELL_SCHEMA = {
    "type": "object",
    "properties": {
        "runs": {"type": "array", "items": RUN_SCHEMA},
        "colspan": {"type": "integer"},
        "rowspan": {"type": "integer"},
        "is_header": {"type": "boolean"},
    },
    "required": ["runs", "colspan", "rowspan", "is_header"],
    "additionalProperties": False,
}

BLOCK_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": BLOCK_TYPES},
        "region": {"type": "string"},
        "heading_level": {"type": "integer"},
        "list_level": {"type": "integer"},
        "list_marker": {"type": "string"},
        "alignment": {"type": "string", "enum": ["left", "center", "right", "justify"]},
        "direction": {"type": "string", "enum": ["ltr", "rtl"]},
        "indent_level": {"type": "integer"},
        "first_line_indent": {"type": "boolean"},
        "font_size_pt": {"type": "number"},
        "font_category": {"type": "string", "enum": FONT_CATEGORIES},
        "box": {"type": "array", "items": {"type": "integer"}},
        "continues_on_next_page": {"type": "boolean"},
        "continues_from_previous_page": {"type": "boolean"},
        "runs": {"type": "array", "items": RUN_SCHEMA},
        "table_rows": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"cells": {"type": "array", "items": CELL_SCHEMA}},
                "required": ["cells"],
                "additionalProperties": False,
            },
        },
        "figure_description": {"type": "string"},
    },
    "required": [
        "type",
        "region",
        "heading_level",
        "list_level",
        "list_marker",
        "alignment",
        "direction",
        "indent_level",
        "first_line_indent",
        "font_size_pt",
        "font_category",
        "box",
        "continues_on_next_page",
        "continues_from_previous_page",
        "runs",
        "table_rows",
        "figure_description",
    ],
    "additionalProperties": False,
}

PAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "regions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "label": {"type": "string"},
                    "kind": {"type": "string", "enum": ["main", "commentary", "sidebar", "column", "other"]},
                    "font_category": {"type": "string", "enum": FONT_CATEGORIES},
                },
                "required": ["id", "label", "kind", "font_category"],
                "additionalProperties": False,
            },
        },
        "blocks": {"type": "array", "items": BLOCK_SCHEMA},
    },
    "required": ["regions", "blocks"],
    "additionalProperties": False,
}

# ---------------------------------------------------------------- validation models


class CRun(BaseModel):
    text: str
    bold: bool
    italic: bool
    underline: bool
    strikethrough: bool
    superscript: bool
    subscript: bool
    color: str
    uncertain: bool


class CCell(BaseModel):
    runs: list[CRun]
    colspan: int
    rowspan: int
    is_header: bool


class CRow(BaseModel):
    cells: list[CCell]


class CBlock(BaseModel):
    type: Literal["heading", "paragraph", "list_item", "table", "caption", "footnote", "header", "footer", "page_number", "quote", "figure"]
    region: str
    heading_level: int
    list_level: int
    list_marker: str
    alignment: Literal["left", "center", "right", "justify"]
    direction: Literal["ltr", "rtl"]
    indent_level: int
    first_line_indent: bool
    font_size_pt: float
    font_category: Literal["serif", "sans-serif", "monospace", "script", "rashi"]
    box: list[int]
    continues_on_next_page: bool
    continues_from_previous_page: bool
    runs: list[CRun]
    table_rows: list[CRow]
    figure_description: str


class CRegion(BaseModel):
    id: str
    label: str
    kind: Literal["main", "commentary", "sidebar", "column", "other"]
    font_category: Literal["serif", "sans-serif", "monospace", "script", "rashi"]


class CPage(BaseModel):
    regions: list[CRegion]
    blocks: list[CBlock]


# ---------------------------------------------------------------- prompt

SYSTEM_PROMPT = """You are the page reader inside ScanToDoc, a tool that turns scanned books and documents into editable, faithfully formatted documents. You receive one page image and describe it as JSON that matches the provided schema. People will read and print the result, so the text must be exactly what is printed and the structure must follow the page.

Text
- Transcribe every printed character exactly: same spelling, punctuation, capitalisation and numbers. Never correct, modernise, translate, summarise or complete text. Keep nikud (vowel points) and ta'amim (cantillation marks) exactly when they are printed, and do not add them when they are not.
- Hebrew, Yiddish and Aramaic are written in logical order, the order a reader reads them. Never reverse characters or words. Mixed lines (Hebrew with English words or numbers) are also in reading order.
- Join the lines of a paragraph with single spaces. Remove a hyphen that only splits an English word across a line break; keep real hyphens and the Hebrew maqaf (־).
- If a word is blurred, cut off or ambiguous, give your best reading and set "uncertain": true on a run that contains just that word.

Blocks
- Split the page into blocks in reading order. Types: heading, paragraph, list_item (one per item), table, caption, footnote, header (running head at the top of the page), footer (running foot), page_number, quote (block quotation, indented on both sides), figure (photo, drawing, chart, diagram, seal or ornament).
- heading_level is 1-4 for headings (1 = most prominent) and 0 otherwise. Headings that look alike get the same level.
- list_marker is the printed bullet or number ("•", "3.", "(ב)") and is not repeated in the runs; list_level is the nesting depth starting at 0.
- alignment is how the block is set: left, center, right or justify. direction is rtl for Hebrew-script paragraphs, ltr otherwise.
- indent_level counts how far the whole block is indented from the text margin (0 = none, 1 = about half an inch, and so on). first_line_indent is true when only the first line is indented.
- font_size_pt is your estimate of the type size in points, using the physical page size you are given. font_category: serif, sans-serif, monospace, script (handwriting-like), or rashi (Hebrew Rashi script).
- box is the block's bounding box [x0, y0, x1, y1] on a 0-1000 scale of the image width and height (0,0 = top-left).
- continues_on_next_page: the last paragraph stops mid-sentence at the bottom of the page. continues_from_previous_page: the first paragraph starts mid-sentence.

Runs
- Split text into runs wherever formatting changes. Mark bold, italic, underline, strikethrough, superscript (footnote markers, exponents) and subscript. color is "#RRGGBB" for clearly coloured text (red, blue, green...) and "" for black or dark grey text.

Tables and figures
- A table block has empty runs and its rows in table_rows; each cell has runs, colspan and rowspan (1 unless merged) and is_header. Other blocks have empty table_rows.
- A figure block has empty runs, its box, and a short figure_description. Text printed inside a picture is part of the figure, not a separate block. A caption is its own block.

Multi-region pages
- When a page holds several separately-flowing texts, such as a Talmud page with the main text and Rashi and Tosafot around it, or a main text with a side commentary, list them in "regions" (id, label such as "Main text", "Rashi", "Tosafot", kind, font_category), set each block's "region" to its region id, and give the blocks region by region (main text first), each in its own reading order. For ordinary pages, "regions" is empty and every "region" is ""."""

TEXT_LAYER_NOTE = """This PDF page also has an embedded text layer. Treat its characters as authoritative for spelling (it may be in a scrambled order and has no formatting); use the image for the order, structure and styling.
<text_layer>
{text}
</text_layer>"""

FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5"}


def make_client():
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - dependency
        raise ReaderError("The 'anthropic' package is not installed.") from exc
    key = config.api_key()
    if not key:
        raise ReaderError(
            "No Claude API key found. Set ANTHROPIC_API_KEY, put it in a .env file, "
            "or add it in the web app's Settings."
        )
    return anthropic.Anthropic(api_key=key, max_retries=3)


class ClaudeReader:
    name = "claude"

    def __init__(self, model: str = costs.DEFAULT_MODEL, effort: str = "medium", client: Any = None):
        self.model = model
        self.effort = effort
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = make_client()
        return self._client

    def cache_key(self) -> str:
        return f"{PROMPT_VERSION}|{self.model}|{self.effort}"

    # ------------------------------------------------------------ request

    def _image_block(self, page: PageInput) -> tuple[dict, tuple[int, int]]:
        with Image.open(page.image_path) as im:
            im = im.convert("RGB")
            size = costs.send_size(im.width, im.height, self.model)
            if size != (im.width, im.height):
                im = im.resize(size, Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=90)
        data = base64.standard_b64encode(buf.getvalue()).decode("ascii")
        return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}, size

    def _user_content(self, page: PageInput) -> list[dict]:
        image, size = self._image_block(page)
        w_in = page.width_px / page.dpi
        h_in = page.height_px / page.dpi
        note = (
            f"Page {page.index + 1}. Physical page size: {w_in:.2f} x {h_in:.2f} inches. "
            f"Image sent: {size[0]} x {size[1]} pixels. Describe this page as JSON."
        )
        content: list[dict] = [image, {"type": "text", "text": note}]
        if page.text_layer and page.text_layer.get("text"):
            content.append({"type": "text", "text": TEXT_LAYER_NOTE.format(text=page.text_layer["text"][:20000])})
        return content

    def _call(self, messages: list[dict]):
        kwargs: dict[str, Any] = dict(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": PAGE_SCHEMA}},
        )
        if self.model in FALLBACK_MODELS:
            # If a safety classifier declines the page, Anthropic re-runs it on a
            # suitable fallback model inside the same request.
            with self.client.beta.messages.stream(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
            ) as stream:
                return stream.get_final_message()
        with self.client.messages.stream(**kwargs) as stream:
            return stream.get_final_message()

    def read(self, page: PageInput) -> PageResult:
        import anthropic

        messages: list[dict] = [{"role": "user", "content": self._user_content(page)}]
        usage = Usage()
        last_error = ""
        for attempt in range(2):
            try:
                response = self._call(messages)
            except anthropic.AuthenticationError as exc:
                raise ReaderError("Claude rejected the API key. Check ANTHROPIC_API_KEY.") from exc
            except anthropic.PermissionDeniedError as exc:
                raise ReaderError(f"The API key is not allowed to use {self.model}.") from exc
            except anthropic.NotFoundError as exc:
                raise ReaderError(f"Unknown Claude model: {self.model}") from exc
            except anthropic.RateLimitError as exc:
                raise ReaderError("Claude's rate limit was reached; try again in a minute or lower concurrency.") from exc
            except anthropic.APIStatusError as exc:
                raise ReaderError(f"Claude API error {exc.status_code}: {exc.message}") from exc
            except anthropic.APIConnectionError as exc:
                raise ReaderError("Could not reach the Claude API. Check the internet connection.") from exc
            usage.add(_usage(response, self.model))
            if response.stop_reason == "refusal":
                category = getattr(getattr(response, "stop_details", None), "category", None)
                raise ReaderError(f"Claude declined to read this page ({category or 'no reason given'}).")
            text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
            if response.stop_reason == "max_tokens":
                last_error = "The page description was too long and got cut off."
            else:
                try:
                    parsed = CPage.model_validate(json.loads(text))
                    blocks, regions = convert(parsed)
                    return PageResult(
                        blocks=blocks, regions=regions, usage=usage, reader="claude", model=self.model, quality=None
                    )
                except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                    last_error = str(exc)[:1500]
            if attempt == 0:
                messages = messages + [
                    {"role": "assistant", "content": response.content},
                    {
                        "role": "user",
                        "content": f"That reply could not be used: {last_error}\nPlease send the complete page description again as valid JSON matching the schema.",
                    },
                ]
        raise ReaderError(f"Claude's reply for this page was not valid after a retry: {last_error[:300]}")


def _usage(response, model: str) -> Usage:
    u = response.usage
    usage = Usage(
        input_tokens=getattr(u, "input_tokens", 0) or 0,
        output_tokens=getattr(u, "output_tokens", 0) or 0,
        cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
        cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
        calls=1,
    )
    usage.cost_usd = costs.cost_of(usage, getattr(response, "model", None) or model)
    return usage


# ---------------------------------------------------------------- conversion


def _run(r: CRun) -> Run:
    color = r.color.strip().upper() if r.color else ""
    if color and not (len(color) == 7 and color.startswith("#")):
        color = ""
    if color in ("#000000", "#111111", "#222222", "#333333"):
        color = ""
    return Run(
        text=r.text,
        bold=r.bold,
        italic=r.italic,
        underline=r.underline,
        strike=r.strikethrough,
        superscript=r.superscript,
        subscript=r.subscript,
        color=color or None,
        uncertain=r.uncertain,
    )


def _box(b: list[int]) -> Optional[tuple[float, float, float, float]]:
    if len(b) != 4:
        return None
    x0, y0, x1, y1 = (max(0, min(1000, v)) / 1000 for v in b)
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1, y1)


def convert(page: CPage) -> tuple[list[Block], list[Region]]:
    regions = [
        Region(id=r.id, label=r.label, kind=r.kind, order=i, font_category=r.font_category)
        for i, r in enumerate(page.regions)
    ]
    region_ids = {r.id for r in regions}
    blocks: list[Block] = []
    for b in page.blocks:
        blk = Block(
            type=b.type,
            level=(min(max(b.heading_level, 1), 4) if b.type == "heading" else max(b.list_level, 0)),
            list_marker=b.list_marker if b.type == "list_item" else "",
            align=b.alignment,
            direction=b.direction,
            indent=max(b.indent_level, 0) * 36.0,
            first_line_indent=18.0 if b.first_line_indent else 0.0,
            font_size=b.font_size_pt if 3 <= b.font_size_pt <= 200 else None,
            font_category=b.font_category,
            runs=[_run(r) for r in b.runs if r.text],
            bbox=_box(b.box),
            region=b.region if b.region in region_ids else ("main" if regions else ""),
            continues=b.continues_on_next_page,
            continued=b.continues_from_previous_page,
        )
        if b.type == "table":
            blk.runs = []
            blk.table = Table(
                rows=[
                    [
                        Cell(
                            runs=[_run(r) for r in c.runs if r.text],
                            colspan=max(c.colspan, 1),
                            rowspan=max(c.rowspan, 1),
                            header=c.is_header,
                        )
                        for c in row.cells
                    ]
                    for row in b.table_rows
                ]
            )
        elif b.type == "figure":
            blk.runs = []
            width = (blk.bbox[2] - blk.bbox[0]) / 0.75 if blk.bbox else 0.5
            blk.figure = Figure(image="", width_frac=round(min(max(width, 0.1), 1.0), 3), description=b.figure_description)
        elif not blk.runs:
            continue
        blocks.append(blk)
    return blocks, regions
