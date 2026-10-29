"""Claude API prices and cost estimates.

Prices are US dollars per million tokens for Anthropic's own API, as listed
in October 2026. They change from time to time; check
https://platform.claude.com/docs/en/about-claude/pricing and update PRICES if
needed. The local and text-layer readers cost nothing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..model import Usage


@dataclass(frozen=True)
class Price:
    label: str
    input: float  # $ per 1M input tokens
    output: float  # $ per 1M output tokens
    high_res: bool  # accepts images up to 2576 px / 3.75 MP


PRICES: dict[str, Price] = {
    "claude-haiku-5-5": Price("Claude Haiku 5.5 — fastest, cheapest", 0.10, 0.50, True),
    "claude-sonnet-5-5": Price("Claude Sonnet 5.5 — balanced", 2.00, 10.00, True),
    "claude-opus-5-5": Price("Claude Opus 5.5 — most accurate", 4.00, 20.00, True),
}
DEFAULT_MODEL = "claude-haiku-5-5"
CACHE_READ = 0.1  # cached prompt tokens cost 10% of the input price
CACHE_WRITE = 1.25  # writing the cache costs 125% of the input price

# Rough sizes used for estimates before any page has been read.
PROMPT_TOKENS = 2600  # system prompt + JSON schema (cached after the first page)
OUTPUT_TOKENS_PER_PAGE = 3500  # the JSON description of a typical book page, plus thinking
TEXT_LAYER_TOKENS = 900


def price_for(model: str) -> Price:
    if model in PRICES:
        return PRICES[model]
    # Unknown model id: assume Sonnet pricing so estimates err on the high side.
    return Price(model, 2.00, 10.00, True)


def send_size(width: int, height: int, model: str) -> tuple[int, int]:
    """The pixel size we send to Claude: as large as the model accepts."""
    hi = price_for(model).high_res
    max_edge, max_pixels = (2576, 3_750_000) if hi else (1568, 1_150_000)
    scale = min(1.0, max_edge / max(width, height), math.sqrt(max_pixels / (width * height)))
    return max(1, int(width * scale)), max(1, int(height * scale))


def image_tokens(width: int, height: int, model: str) -> int:
    w, h = send_size(width, height, model)
    return int(math.ceil(w * h / 784))


def cost_of(usage: Usage, model: str) -> float:
    p = price_for(model)
    return (
        usage.input_tokens * p.input
        + usage.cache_write_tokens * p.input * CACHE_WRITE
        + usage.cache_read_tokens * p.input * CACHE_READ
        + usage.output_tokens * p.output
    ) / 1_000_000


def estimate_pages(n_pages: int, model: str, width: int = 2550, height: int = 3300, text_layer_pages: int = 0) -> dict:
    """Estimated cost of reading n pages with Claude (before anything is sent)."""
    if n_pages <= 0:
        return {"pages": 0, "low": 0.0, "high": 0.0, "typical": 0.0, "per_page": 0.0}
    p = price_for(model)
    img = image_tokens(width, height, model)
    per_page_in = img + 150 + PROMPT_TOKENS * CACHE_READ
    first_extra = PROMPT_TOKENS * (CACHE_WRITE - CACHE_READ)
    typical = (
        n_pages * per_page_in * p.input
        + first_extra * p.input
        + text_layer_pages * TEXT_LAYER_TOKENS * p.input
        + n_pages * OUTPUT_TOKENS_PER_PAGE * p.output
    ) / 1_000_000
    return {
        "pages": n_pages,
        "model": model,
        "per_page": round(typical / n_pages, 5),
        "typical": round(typical, 4),
        # Sparse pages cost less, dense pages (small print, commentaries) more.
        "low": round(typical * 0.5, 4),
        "high": round(typical * 2.5, 4),
    }


def format_usd(x: float) -> str:
    if x == 0:
        return "$0"
    if x < 0.01:
        return f"${x:.4f}"
    if x < 1:
        return f"${x:.3f}"
    return f"${x:,.2f}"
