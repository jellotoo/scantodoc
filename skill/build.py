"""Build the ScanToDoc skill: refresh reference/options.md from the command
line's own help, put a wheel of the package inside the skill, and zip the
skill folder for upload to the Claude app.

    python skill/build.py            ->  skill/dist/scantodoc-skill.zip
    python skill/build.py --options  (only refresh reference/options.md)
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SKILL = HERE / "scantodoc"
COMMANDS = ["convert", "restyle", "batch", "prepare", "assemble", "zoom", "estimate", "serve", "preset", "fonts", "projects", "doctor"]


def help_text(*args: str) -> str:
    import click
    from scantodoc.cli import main

    cmd = main
    ctx = click.Context(main, info_name="scantodoc", terminal_width=100, **main.context_settings)
    for a in args:
        cmd = cmd.commands[a]
        ctx = click.Context(cmd, info_name=a, parent=ctx, **cmd.context_settings)
    return cmd.get_help(ctx)


def options_markdown() -> str:
    out = [
        "# ScanToDoc command reference",
        "",
        "Generated from `scantodoc COMMAND --help` by `skill/build.py`; do not edit by hand.",
        "Run commands through `scripts/run.py`, e.g. `python3 scripts/run.py convert book.pdf`.",
        "",
    ]
    for name in COMMANDS:
        out += [f"## {name}", "", "```text", help_text(name).rstrip(), "```", ""]
        from scantodoc.cli import main

        sub = getattr(main.commands[name], "commands", {})
        for s in sub:
            out += [f"### {name} {s}", "", "```text", help_text(name, s).rstrip(), "```", ""]
    return "\n".join(out)


def write_options() -> Path:
    path = SKILL / "reference" / "options.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text(options_markdown(), encoding="utf-8")
    return path


def build() -> Path:
    print("Wrote", write_options())
    wheels = SKILL / "wheels"
    shutil.rmtree(wheels, ignore_errors=True)
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "--quiet", "-w", str(wheels), str(ROOT)], check=True
    )
    shutil.rmtree(ROOT / "build", ignore_errors=True)
    print("Built", *[w.name for w in wheels.iterdir()])
    dist = HERE / "dist"
    dist.mkdir(exist_ok=True)
    target = dist / "scantodoc-skill.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(SKILL.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                z.write(f, Path("scantodoc") / f.relative_to(SKILL))
    print("Wrote", target, f"({target.stat().st_size / 1e6:.1f} MB)")
    return target


if __name__ == "__main__":
    if "--options" in sys.argv:
        print("Wrote", write_options())
    else:
        build()
