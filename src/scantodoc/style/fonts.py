"""The curated font list, default fonts per detected category, and CSS fallbacks.

Word (.docx) files only name a font; Word uses it if it is installed on the
reader's computer. HTML and PDF exports also carry ScanToDoc's bundled free
fonts, so they look right everywhere.
"""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path
from typing import Optional

FONTS_DIR = Path(__file__).resolve().parents[1] / "fonts"

# name, script ("latin" / "hebrew" / "both"), category, where it comes from
CURATED: list[dict] = [
    # Latin
    {"name": "Times New Roman", "script": "both", "category": "serif", "source": "Windows, Mac"},
    {"name": "Georgia", "script": "latin", "category": "serif", "source": "Windows, Mac"},
    {"name": "Garamond", "script": "latin", "category": "serif", "source": "Windows (Office)"},
    {"name": "EB Garamond", "script": "latin", "category": "serif", "source": "bundled (free)"},
    {"name": "Cambria", "script": "latin", "category": "serif", "source": "Windows, Mac (Office)"},
    {"name": "Book Antiqua", "script": "latin", "category": "serif", "source": "Windows (Office)"},
    {"name": "Palatino Linotype", "script": "latin", "category": "serif", "source": "Windows"},
    {"name": "Calibri", "script": "latin", "category": "sans-serif", "source": "Windows, Mac (Office)"},
    {"name": "Aptos", "script": "latin", "category": "sans-serif", "source": "Office 365"},
    {"name": "Arial", "script": "both", "category": "sans-serif", "source": "Windows, Mac"},
    {"name": "Segoe UI", "script": "both", "category": "sans-serif", "source": "Windows"},
    {"name": "Helvetica", "script": "latin", "category": "sans-serif", "source": "Mac"},
    {"name": "Verdana", "script": "latin", "category": "sans-serif", "source": "Windows, Mac"},
    {"name": "Courier New", "script": "both", "category": "monospace", "source": "Windows, Mac"},
    {"name": "Consolas", "script": "latin", "category": "monospace", "source": "Windows"},
    # Hebrew
    {"name": "Frank Ruehl CLM", "script": "hebrew", "category": "serif", "source": "free (Culmus)"},
    {"name": "Frank Ruhl Libre", "script": "hebrew", "category": "serif", "source": "bundled (free)"},
    {"name": "FrankRuehl", "script": "hebrew", "category": "serif", "source": "Windows"},
    {"name": "David", "script": "hebrew", "category": "serif", "source": "Windows"},
    {"name": "David CLM", "script": "hebrew", "category": "serif", "source": "free (Culmus)"},
    {"name": "David Libre", "script": "hebrew", "category": "serif", "source": "bundled (free)"},
    {"name": "Narkisim", "script": "hebrew", "category": "serif", "source": "Windows"},
    {"name": "Taamey Frank CLM", "script": "hebrew", "category": "serif", "source": "free (Culmus), supports ta'amim"},
    {"name": "Keter YG", "script": "hebrew", "category": "serif", "source": "free (Culmus)"},
    {"name": "Noto Serif Hebrew", "script": "hebrew", "category": "serif", "source": "bundled (free)"},
    {"name": "SBL Hebrew", "script": "hebrew", "category": "serif", "source": "free (SBL)"},
    {"name": "Ezra SIL", "script": "hebrew", "category": "serif", "source": "free (SIL)"},
    {"name": "Miriam", "script": "hebrew", "category": "sans-serif", "source": "Windows"},
    {"name": "Miriam CLM", "script": "hebrew", "category": "sans-serif", "source": "free (Culmus)"},
    {"name": "Heebo", "script": "hebrew", "category": "sans-serif", "source": "bundled (free)"},
    {"name": "Alef", "script": "hebrew", "category": "sans-serif", "source": "bundled (free)"},
    {"name": "Noto Sans Hebrew", "script": "hebrew", "category": "sans-serif", "source": "bundled (free)"},
    {"name": "Arial Hebrew", "script": "hebrew", "category": "sans-serif", "source": "Mac"},
    {"name": "Noto Rashi Hebrew", "script": "hebrew", "category": "rashi", "source": "bundled (free) — Rashi script"},
    {"name": "Miriam Mono CLM", "script": "hebrew", "category": "monospace", "source": "free (Culmus)"},
]

# What "keep detected" means for each font category, in Word and in CSS.
DEFAULT_LATIN = {
    "serif": "Times New Roman",
    "sans-serif": "Arial",
    "monospace": "Courier New",
    "script": "Times New Roman",
    "rashi": "Times New Roman",
}
DEFAULT_HEBREW = {
    "serif": "David",
    "sans-serif": "Arial",
    "monospace": "Courier New",
    "script": "David",
    "rashi": "Noto Rashi Hebrew",
}

BUNDLED: dict[str, list[tuple[str, str, str]]] = {
    # family -> [(file, weight range, style)]
    "Frank Ruhl Libre": [("FrankRuhlLibre-Variable.ttf", "300 900", "normal")],
    "David Libre": [
        ("DavidLibre-Regular.ttf", "400", "normal"),
        ("DavidLibre-Medium.ttf", "500", "normal"),
        ("DavidLibre-Bold.ttf", "700", "normal"),
    ],
    "Noto Rashi Hebrew": [("NotoRashiHebrew-Variable.ttf", "100 900", "normal")],
    "Noto Serif Hebrew": [("NotoSerifHebrew-Variable.ttf", "100 900", "normal")],
    "Noto Sans Hebrew": [("NotoSansHebrew-Variable.ttf", "100 900", "normal")],
    "Heebo": [("Heebo-Variable.ttf", "100 900", "normal")],
    "Alef": [("Alef-Regular.ttf", "400", "normal"), ("Alef-Bold.ttf", "700", "normal")],
    "EB Garamond": [("EBGaramond-Variable.ttf", "400 800", "normal"), ("EBGaramond-Italic-Variable.ttf", "400 800", "italic")],
}

# Free stand-ins appended to a font's CSS stack, so HTML/PDF never fall back to
# a random system font when the chosen one is not installed.
LOOKALIKES: dict[str, list[str]] = {
    "frank ruehl clm": ["Frank Ruhl Libre"],
    "frankruehl": ["Frank Ruehl CLM", "Frank Ruhl Libre"],
    "frank ruehl": ["Frank Ruehl CLM", "FrankRuehl", "Frank Ruhl Libre"],
    "frank ruhl libre": [],
    "taamey frank clm": ["Frank Ruehl CLM", "Frank Ruhl Libre"],
    "david": ["David CLM", "David Libre"],
    "david clm": ["David", "David Libre"],
    "narkisim": ["David Libre"],
    "keter yg": ["Frank Ruhl Libre"],
    "miriam": ["Miriam CLM", "Heebo"],
    "miriam clm": ["Miriam", "Heebo"],
    "arial hebrew": ["Arial", "Heebo"],
    "garamond": ["EB Garamond"],
    "times new roman": ["Tinos", "Liberation Serif"],
    "arial": ["Liberation Sans", "Arimo", "Heebo"],
    "courier new": ["Liberation Mono", "Cousine"],
    "calibri": ["Carlito", "Heebo"],
    "cambria": ["Caladea", "Georgia"],
}
GENERIC = {"serif": "serif", "sans-serif": "sans-serif", "monospace": "monospace", "script": "cursive", "rashi": "serif"}
HEBREW_GENERIC = {
    "serif": ["Frank Ruhl Libre", "Noto Serif Hebrew"],
    "sans-serif": ["Heebo", "Noto Sans Hebrew"],
    "monospace": ["Miriam Mono CLM"],
    "script": ["Frank Ruhl Libre"],
    "rashi": ["Noto Rashi Hebrew"],
}


def font_stack(name: str, category: str = "serif", hebrew: bool = False) -> list[str]:
    stack = [name]
    stack += LOOKALIKES.get(name.lower(), [])
    if hebrew:
        stack += HEBREW_GENERIC.get(category, [])
    stack.append(GENERIC.get(category, "serif"))
    seen, out = set(), []
    for f in stack:
        if f.lower() not in seen:
            seen.add(f.lower())
            out.append(f)
    return out


def css_family(stack: list[str]) -> str:
    generic = {"serif", "sans-serif", "monospace", "cursive"}
    return ", ".join(f if f in generic else f'"{f}"' for f in stack)


def bundled_families_in(stacks: list[list[str]]) -> list[str]:
    """The bundled fonts worth shipping: the first bundled stand-in of each stack."""
    wanted = []
    for stack in stacks:
        for f in stack:
            if f in BUNDLED:
                if f not in wanted:
                    wanted.append(f)
                break
    return wanted


@lru_cache(maxsize=32)
def _data_uri(filename: str) -> str:
    data = (FONTS_DIR / filename).read_bytes()
    return "data:font/ttf;base64," + base64.b64encode(data).decode("ascii")


def font_face_css(families: list[str], mode: str = "embed", url_prefix: Optional[str] = None) -> str:
    """@font-face rules for bundled fonts. mode: embed (data URIs), file (file:// URLs), url (prefix)."""
    rules = []
    for fam in families:
        for filename, weight, style in BUNDLED.get(fam, []):
            if mode == "embed":
                src = _data_uri(filename)
            elif mode == "file":
                src = (FONTS_DIR / filename).as_uri()
            else:
                src = f"{url_prefix or '/fonts/'}{filename}"
            rules.append(
                f'@font-face{{font-family:"{fam}";src:local("{fam}"),url("{src}") format("truetype");'
                f"font-weight:{weight};font-style:{style};font-display:swap}}"
            )
    return "\n".join(rules)


def curated() -> list[dict]:
    return [dict(f, bundled=f["name"] in BUNDLED) for f in CURATED]
