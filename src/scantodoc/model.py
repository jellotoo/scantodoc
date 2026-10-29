"""The document model: ScanToDoc's internal description of a converted document.

Every reader (local OCR, the PDF text layer, Claude) produces this model, and
every exporter consumes it. Styling choices are *not* stored here: they are
applied at export time, so a document can be re-styled any number of times
without reading the scans again.

Coordinates (``bbox``) are fractions of the page (0.0-1.0, origin top-left),
so they stay valid whatever resolution the page image is shown at.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

BlockType = Literal[
    "heading",
    "paragraph",
    "list_item",
    "table",
    "caption",
    "footnote",
    "header",
    "footer",
    "page_number",
    "quote",
    "figure",
]
BLOCK_TYPES: tuple[str, ...] = BlockType.__args__  # type: ignore[attr-defined]

Alignment = Literal["left", "center", "right", "justify"]
Direction = Literal["ltr", "rtl"]
FontCategory = Literal["serif", "sans-serif", "monospace", "script", "rashi"]
ReaderName = Literal["local", "textlayer", "claude", "agent", "import"]

SCHEMA_VERSION = 1


def new_id() -> str:
    return uuid.uuid4().hex[:10]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Run(BaseModel):
    """A stretch of text with uniform formatting."""

    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False
    superscript: bool = False
    subscript: bool = False
    color: Optional[str] = None  # "#RRGGBB"; None means ordinary black/dark text
    uncertain: bool = False  # the reader was not sure about this text
    confidence: Optional[float] = None  # 0-100 when the reader reports one


class Cell(BaseModel):
    runs: list[Run] = Field(default_factory=list)
    colspan: int = 1
    rowspan: int = 1
    header: bool = False
    align: Optional[Alignment] = None


class Table(BaseModel):
    rows: list[list[Cell]] = Field(default_factory=list)
    borders: bool = True


class Figure(BaseModel):
    image: str  # path relative to the project folder, or a data: URI in exports
    width_frac: float = 0.5  # share of the text width the figure occupied on the page
    description: str = ""


class Block(BaseModel):
    id: str = Field(default_factory=new_id)
    type: BlockType = "paragraph"
    level: int = 0  # heading level 1-4, or list nesting level (0 = top)
    list_marker: str = ""  # the bullet or number as printed, e.g. "•", "3.", "(ב)"
    align: Alignment = "left"
    direction: Direction = "ltr"
    indent: float = 0.0  # left/start indent in points
    first_line_indent: float = 0.0  # points; negative = hanging indent
    font_size: Optional[float] = None  # points, as detected
    font_category: FontCategory = "serif"
    runs: list[Run] = Field(default_factory=list)
    table: Optional[Table] = None
    figure: Optional[Figure] = None
    bbox: Optional[tuple[float, float, float, float]] = None  # x0, y0, x1, y1 fractions
    region: str = ""  # region id for multi-region layouts ("" = main flow)
    continues: bool = False  # this paragraph carries on at the top of the next page
    continued: bool = False  # this paragraph is the carry-over from the previous page
    space_before: Optional[float] = None  # detected gap above, points
    user_edited: bool = False  # set once a person has corrected this block

    @property
    def text(self) -> str:
        if self.table is not None:
            return "\n".join(
                "\t".join("".join(r.text for r in c.runs) for c in row) for row in self.table.rows
            )
        return "".join(r.text for r in self.runs)


class Region(BaseModel):
    """A separately flowing area of a page, e.g. the main text and Rashi on a Gemara daf."""

    id: str
    label: str = ""  # e.g. "Main text", "Rashi", "Tosafos"
    kind: Literal["main", "commentary", "sidebar", "column", "other"] = "main"
    order: int = 0
    font_category: Optional[FontCategory] = None


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    calls: int = 0

    def add(self, other: "Usage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.cache_write_tokens += other.cache_write_tokens
        self.cost_usd += other.cost_usd
        self.calls += other.calls


class Page(BaseModel):
    index: int  # 0-based position in the document
    source: str = ""  # file the page came from
    source_page: int = 0  # page number inside that file (0-based)
    image: str = ""  # page image, relative to the project folder
    width_px: int = 0
    height_px: int = 0
    dpi: int = 300
    has_text_layer: bool = False
    regions: list[Region] = Field(default_factory=list)
    blocks: list[Block] = Field(default_factory=list)
    reader: Optional[ReaderName] = None
    model: str = ""  # Claude model id when the Claude reader was used
    status: Literal["pending", "reading", "done", "error"] = "pending"
    error: str = ""
    quality: Optional[float] = None  # 0-100, the reader's own confidence for the page
    usage: Usage = Field(default_factory=Usage)

    @property
    def width_pt(self) -> float:
        return self.width_px * 72.0 / self.dpi if self.dpi else 612.0

    @property
    def height_pt(self) -> float:
        return self.height_px * 72.0 / self.dpi if self.dpi else 792.0


class DetectedStyle(BaseModel):
    """The document-wide, normalised look of one kind of element."""

    font_size: Optional[float] = None
    font_category: FontCategory = "serif"
    bold: bool = False
    italic: bool = False
    color: Optional[str] = None
    align: Optional[Alignment] = None


class Document(BaseModel):
    schema_version: int = SCHEMA_VERSION
    id: str = Field(default_factory=new_id)
    title: str = ""
    created: str = Field(default_factory=now_iso)
    updated: str = Field(default_factory=now_iso)
    pages: list[Page] = Field(default_factory=list)
    detected: dict[str, DetectedStyle] = Field(default_factory=dict)
    main_direction: Direction = "ltr"
    usage: Usage = Field(default_factory=Usage)

    def touch(self) -> None:
        self.updated = now_iso()

    def iter_blocks(self):
        for page in self.pages:
            for block in page.blocks:
                yield page, block

    def find_block(self, block_id: str) -> tuple[Optional[Page], Optional[Block]]:
        for page, block in self.iter_blocks():
            if block.id == block_id:
                return page, block
        return None, None

    def total_usage(self) -> Usage:
        total = Usage()
        for page in self.pages:
            total.add(page.usage)
        return total


def element_key(block: Block) -> str:
    """The style bucket a block belongs to: body, h1-h4, list, table, caption..."""
    if block.type == "heading":
        return f"h{min(max(block.level, 1), 4)}"
    if block.type == "paragraph":
        return "body"
    if block.type == "list_item":
        return "list"
    return block.type


ELEMENT_KEYS: tuple[str, ...] = (
    "body",
    "h1",
    "h2",
    "h3",
    "h4",
    "list",
    "table",
    "caption",
    "footnote",
    "quote",
    "header",
    "footer",
)
