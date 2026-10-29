"""Named style presets: four built in, plus any you save (as JSON files in
~/ScanToDoc/presets). A preset only lists the options it changes; everything
else stays at "keep what was detected"."""

from __future__ import annotations

import json
from pathlib import Path

from .. import config
from ..project import slugify
from .options import StyleOptions, merge

BUILTIN_DIR = Path(__file__).resolve().parent / "presets"
BUILTIN_ORDER = ["keep-original", "clean-modern", "classic-sefer", "academic"]


def _key(name: str) -> str:
    return slugify(name)


def _builtin() -> dict[str, dict]:
    out = {}
    for stem in BUILTIN_ORDER:
        path = BUILTIN_DIR / f"{stem}.json"
        out[stem] = json.loads(path.read_text(encoding="utf-8"))
    return out


def _user() -> dict[str, dict]:
    out = {}
    for path in sorted(config.presets_dir().glob("*.json")):
        try:
            out[path.stem] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return out


def list_presets() -> list[dict]:
    items = [{"key": k, "name": v.get("name", k), "description": v.get("description", ""), "builtin": True} for k, v in _builtin().items()]
    items += [{"key": k, "name": v.get("name", k), "description": v.get("description", ""), "builtin": False} for k, v in _user().items()]
    return items


def load(name_or_path: str) -> StyleOptions:
    """Load a preset by name ("Classic sefer"), key ("classic-sefer") or JSON file path."""
    p = Path(name_or_path).expanduser()
    if p.suffix.lower() == ".json" and p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        if "style" in data and "document" in data:  # an exported .scantodoc.json bundle
            data = data["style"]
        return merge(StyleOptions(), data)
    key = _key(name_or_path)
    for source in (_user(), _builtin()):
        if key in source:
            return merge(StyleOptions(), source[key])
        for k, v in source.items():
            if _key(v.get("name", "")) == key:
                return merge(StyleOptions(), v)
    names = ", ".join(f'"{i["name"]}"' for i in list_presets())
    raise KeyError(f'No preset called "{name_or_path}". Available: {names}')


def save(style: StyleOptions, name: str, description: str = "") -> Path:
    data = style.model_dump(exclude_defaults=True)
    data["name"] = name
    if description:
        data["description"] = description
    path = config.presets_dir() / f"{_key(name)}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def delete(name: str) -> bool:
    path = config.presets_dir() / f"{_key(name)}.json"
    if path.exists():
        path.unlink()
        return True
    return False
