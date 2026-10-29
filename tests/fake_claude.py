"""A stand-in for the Claude API used by the tests.

It answers each page request with the sample's answer key (the exact layout
the sample page was rendered from), so the tests can check that everything
after the API call - validation, conversion, normalisation, styling and
export - keeps headings, bold, sizes, colours and right-to-left text intact,
without spending money or needing a key.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

SAMPLES = Path(__file__).parent / "samples"


def answer_pages(name: str) -> list[dict]:
    data = json.loads((SAMPLES / f"{name}.answer.json").read_text(encoding="utf-8"))
    pages = []
    for page in data["pages"]:
        blocks = []
        for b in page["blocks"]:
            b = dict(b)
            b["box"] = [int(round(v * 1000)) for v in b.pop("bbox_frac")]
            blocks.append(b)
        pages.append({"regions": page["regions"], "blocks": blocks})
    return pages


class _Stream:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.message


class FakeClaude:
    """Mimics `anthropic.Anthropic()` closely enough for ClaudeReader."""

    def __init__(self, pages: list[dict], bad_first: int = 0, refuse: bool = False, model: str = "claude-haiku-5-5"):
        self.pages = pages
        self.bad_first = bad_first  # how many replies to send back as broken JSON first
        self.refuse = refuse
        self.model = model
        self.calls: list[dict] = []
        self.messages = SimpleNamespace(stream=self._stream)
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kwargs):
        self.calls.append(kwargs)
        note = next(
            c["text"] for c in kwargs["messages"][0]["content"] if c.get("type") == "text" and c["text"].startswith("Page ")
        )
        index = int(re.match(r"Page (\d+)\.", note).group(1)) - 1
        usage = SimpleNamespace(
            input_tokens=4000, output_tokens=3000, cache_read_input_tokens=2000, cache_creation_input_tokens=0
        )
        if self.refuse:
            msg = SimpleNamespace(
                content=[], stop_reason="refusal", usage=usage, model=self.model,
                stop_details=SimpleNamespace(category="general_harms"),
            )
            return _Stream(msg)
        if self.bad_first > 0:
            self.bad_first -= 1
            text = '{"regions": [], "blocks": [{"type": "paragraph"'  # cut off
        else:
            text = json.dumps(self.pages[index], ensure_ascii=False)
        msg = SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn", usage=usage, model=self.model
        )
        return _Stream(msg)
