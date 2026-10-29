"""Reader for PDF pages that already contain real text (no OCR needed).

The words, fonts, sizes, bold/italic and colours come straight from the PDF;
the page image is still used for tables, figures and underlines.
"""

from __future__ import annotations

from .. import layout, measure
from .base import PageInput, PageResult, ReaderError

TEXTLAYER_VERSION = "textlayer-1"


class TextLayerReader:
    name = "textlayer"

    def cache_key(self) -> str:
        return TEXTLAYER_VERSION

    def read(self, page: PageInput) -> PageResult:
        layer = page.text_layer
        if not layer or not layer.get("words"):
            raise ReaderError("This page has no text layer.")
        styled = not layer.get("ocr_layer")
        words = []
        for w in layer["words"]:
            x0, y0, x1, y1 = w["bbox"]
            word = layout.Word(text=w["text"], x0=x0, y0=y0, x1=x1, y1=y1, conf=None, key=tuple(w["key"]))
            if styled:
                word.size_pt = w.get("size") or None
                word.bold = w.get("bold", False)
                word.italic = w.get("italic", False)
                word.color = w.get("color")
                word.superscript = w.get("superscript", False)
                word.font_category = w.get("category")
            words.append(word)
        img = measure.load_page(page.image_path)
        result = layout.analyze(words, img, page.dpi, page.width_px, page.height_px)
        warnings = []
        if layer.get("visual_order_fixed"):
            warnings.append("This PDF stored Hebrew text backwards; it was put back into reading order.")
        return PageResult(
            blocks=result.blocks, regions=result.regions, quality=100.0, reader="textlayer", warnings=warnings
        )
