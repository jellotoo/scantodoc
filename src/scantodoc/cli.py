"""The `scantodoc` command line.

    scantodoc convert scan.pdf --format docx,md --preset "Classic sefer"
    scantodoc restyle my-book.scantodoc.json --preset "Clean modern" --format pdf
    scantodoc batch ./scans --format docx
    scantodoc serve

Run `scantodoc COMMAND --help` for every option.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Optional

import click

from . import __version__, config
from .engine import cost as costs
from .engine import ingest, tesseract
from .engine.pipeline import READERS, ConvertSettings, convert
from .export import EXTENSIONS, FORMATS, export, load_bundle, normalize_format
from .project import Project, list_projects
from .style import fonts as font_list
from .style import presets
from .style.options import StyleOptions, set_path

CONTEXT = {"help_option_names": ["-h", "--help"], "max_content_width": 100}
ELEMENT_CHOICES = ["body", "h1", "h2", "h3", "h4", "list", "table", "caption", "footnote", "quote"]


def _echo_err(msg: str) -> None:
    click.secho(msg, fg="red", err=True)


# ---------------------------------------------------------------- shared options


def reading_options(f: Callable) -> Callable:
    opts = [
        click.option("--reader", type=click.Choice(READERS), default="local", show_default=True,
                     help="How pages are read. local = free Tesseract OCR on this computer (no internet); "
                          "claude = Claude AI (best quality, costs money, needs ANTHROPIC_API_KEY); "
                          "hybrid = local first, Claude only for pages the local reader struggles with."),
        click.option("--model", default=costs.DEFAULT_MODEL, show_default=True,
                     help="Claude model for the claude/hybrid readers: claude-haiku-5-5 (cheapest), "
                          "claude-sonnet-5-5, or claude-opus-5-5 (most accurate)."),
        click.option("--effort", type=click.Choice(["low", "medium", "high", "xhigh", "max"]), default="medium",
                     show_default=True, help="How hard Claude thinks about each page. Higher costs more."),
        click.option("--languages", default="eng+heb", show_default=True,
                     help="Tesseract languages for the local reader, joined with '+'. Add 'yid' for Yiddish "
                          "(needs the Yiddish language pack)."),
        click.option("--pages", default=None, help="Only these pages, e.g. '1-10,15' (counting from 1)."),
        click.option("--dpi", type=int, default=300, show_default=True, help="Resolution for page images."),
        click.option("--concurrency", type=int, default=4, show_default=True, help="Pages read at the same time."),
        click.option("--hybrid-threshold", type=float, default=85.0, show_default=True,
                     help="Hybrid reader: pages whose local reading scores below this (0-100) go to Claude."),
        click.option("--no-text-layer", is_flag=True, help="Ignore text already inside the PDF and read the images."),
        click.option("--force", is_flag=True, help="Read pages again even if they were read before (uses the API again)."),
        click.option("--yes", "-y", is_flag=True, help="Do not ask before spending money on Claude."),
        click.option("--max-cost", type=float, default=None,
                     help="Stop before starting if the estimated Claude cost (US$) is above this."),
    ]
    for o in reversed(opts):
        f = o(f)
    return f


def output_options(f: Callable) -> Callable:
    opts = [
        click.option("--format", "-f", "formats", default="docx", show_default=True,
                     help="Comma-separated export formats: " + ", ".join(FORMATS) + "."),
        click.option("--out", "-o", type=click.Path(path_type=Path), default=None,
                     help="Folder for the exported files (default: next to the input)."),
    ]
    for o in reversed(opts):
        f = o(f)
    return f


def style_options(f: Callable) -> Callable:
    opts = [
        click.option("--preset", default=None,
                     help='A style preset name ("Keep original", "Clean modern", "Classic sefer", "Academic", '
                          "or one you saved) or a preset .json file. Other style options are applied on top."),
        # fonts
        click.option("--body-font", default=None, help="Font for all Latin-script text (e.g. 'Times New Roman', 'Garamond')."),
        click.option("--hebrew-font", default=None, help="Font for all Hebrew/Yiddish/Aramaic text (e.g. 'Frank Ruehl CLM', 'David')."),
        click.option("--heading-font", default=None, help="Latin font for all headings."),
        click.option("--heading-hebrew-font", default=None, help="Hebrew font for all headings."),
        click.option("--element-font", multiple=True, metavar="ELEMENT=FONT",
                     help="Latin font for one element: h1, h2, h3, h4, list, table, caption, footnote or quote. "
                          "Repeat as needed, e.g. --element-font h1=Georgia."),
        click.option("--element-hebrew-font", multiple=True, metavar="ELEMENT=FONT",
                     help="Hebrew font for one element, e.g. --element-hebrew-font footnote=David."),
        click.option("--rashi-font", default=None, help="Font for text detected in Rashi script (default: Noto Rashi Hebrew)."),
        # sizes
        click.option("--scale", type=float, default=None, help="Scale every detected size, in percent (e.g. 110)."),
        click.option("--size", "sizes", multiple=True, metavar="ELEMENT=PT",
                     help="Exact size in points for an element (body, h1-h4, list, table, caption, footnote, quote). "
                          "Repeatable or comma-separated: --size body=12,h1=24. Elements not given keep their detected size."),
        # colours
        click.option("--black", is_flag=True, help="Make all text black (ignore detected colours)."),
        click.option("--heading-color", default=None, metavar="#RRGGBB", help="Colour for all headings."),
        click.option("--color", "colors", multiple=True, metavar="ELEMENT=#RRGGBB",
                     help="Colour for one element: body, h1-h4, list, quote, caption, footnote. Repeatable."),
        click.option("--link-color", default=None, metavar="#RRGGBB", help="Colour for web links."),
        click.option("--background", default=None, metavar="#RRGGBB", help="Page background colour."),
        click.option("--accent-color", default=None, metavar="#RRGGBB", help="Colour of a line under or beside headings."),
        click.option("--accent-style", type=click.Choice(["underline", "rule", "bar"]), default=None,
                     help="Heading accent: underline (thick line below), rule (thin line below) or bar (beside)."),
        # emphasis
        click.option("--strip-bold", is_flag=True, help="Remove bold from the text (headings keep their heading look)."),
        click.option("--strip-italic", is_flag=True, help="Remove italic."),
        click.option("--strip-underline", is_flag=True, help="Remove underline."),
        click.option("--bold-to-headings", type=click.IntRange(1, 4), default=None, metavar="LEVEL",
                     help="Turn short lines that are entirely bold into real headings of this level (1-4)."),
        # spacing & layout
        click.option("--line-spacing", type=float, default=None, help="Line spacing as a multiple (1 = single, 1.5, 2 = double)."),
        click.option("--space-before", type=float, default=None, help="Space before each paragraph, in points."),
        click.option("--space-after", type=float, default=None, help="Space after each paragraph, in points."),
        click.option("--first-line-indent", type=float, default=None, help="First-line indent of paragraphs, in points (0 = none)."),
        click.option("--margins", default=None, metavar="INCHES",
                     help="Page margins in inches: one value for all sides, or top,right,bottom,left."),
        click.option("--page-size", default=None, metavar="SIZE",
                     help="letter, a4, legal, a5, or WIDTHxHEIGHT in inches (e.g. 6x9). Default: like the scan."),
        click.option("--orientation", type=click.Choice(["portrait", "landscape"]), default=None, help="Page orientation."),
        click.option("--columns", type=click.IntRange(1, 3), default=None, help="Text columns per page (1-3)."),
        click.option("--align", type=click.Choice(["keep", "start", "left", "right", "justify"]), default=None,
                     help="Paragraph alignment. start = left for English, right for Hebrew. keep = as scanned."),
        click.option("--align-headings", is_flag=True, help="Also apply --align to headings (normally they keep theirs)."),
        # extras
        click.option("--toc", is_flag=True, help="Add a table of contents built from the headings."),
        click.option("--page-numbers", is_flag=True, help="Add page numbers in the footer."),
        click.option("--title-page", is_flag=True, help="Add a title page (see --title, --subtitle, --author)."),
        click.option("--title", default=None, help="Document title (title page and file properties)."),
        click.option("--subtitle", default=None, help="Subtitle for the title page."),
        click.option("--author", default=None, help="Author for the title page and file properties."),
        click.option("--keep-headers", is_flag=True, help="Keep the running headers and footers printed on the scanned pages."),
        click.option("--keep-page-numbers", is_flag=True, help="Keep the scan's own printed page numbers."),
        click.option("--no-merge-pages", is_flag=True, help="Do not join paragraphs that a page break split in two."),
        click.option("--strip-nikud", is_flag=True, help="Remove Hebrew vowel points (nikud)."),
        click.option("--strip-teamim", is_flag=True, help="Remove cantillation marks (ta'amim)."),
        click.option("--no-figures", is_flag=True, help="Leave out pictures cropped from the pages."),
        click.option("--regions", type=click.Choice(["per-page", "grouped", "main-only"]), default=None,
                     help="Pages with several texts (e.g. Gemara with Rashi): per-page = main text then each "
                          "commentary, page by page; grouped = all main text, then each commentary; main-only."),
        click.option("--highlight-uncertain", is_flag=True, help="Highlight words the reader was unsure of (for proofreading)."),
        click.option("--set", "sets", multiple=True, metavar="PATH=VALUE",
                     help="Set any style option by its path, e.g. --set extras.toc_title=Inhalt. Repeatable."),
    ]
    for o in reversed(opts):
        f = o(f)
    return f


def _pairs(values: tuple[str, ...], what: str) -> list[tuple[str, str]]:
    out = []
    for v in values:
        for part in v.split(","):
            part = part.strip()
            if not part:
                continue
            if "=" not in part:
                raise click.BadParameter(f"expected ELEMENT=VALUE, got '{part}'", param_hint=what)
            k, val = part.split("=", 1)
            out.append((k.strip().lower(), val.strip()))
    return out


def build_style(base: Optional[StyleOptions] = None, **kw: Any) -> StyleOptions:
    """Combine a preset (or a base style) with the style flags given on the command line."""
    if kw.get("preset"):
        try:
            s = presets.load(kw["preset"])
        except KeyError as exc:
            raise click.BadParameter(str(exc.args[0]), param_hint="--preset")
    else:
        s = base or StyleOptions()

    def put(path: str, value: Any) -> None:
        nonlocal s
        try:
            s = set_path(s, path, value)
        except Exception as exc:  # pydantic validation
            raise click.BadParameter(f"{value!r}: {exc}", param_hint=path)

    simple = {
        "body_font": "fonts.body.latin",
        "hebrew_font": "fonts.body.hebrew",
        "heading_font": "fonts.headings.latin",
        "heading_hebrew_font": "fonts.headings.hebrew",
        "rashi_font": "fonts.elements.rashi.hebrew",
        "link_color": "colors.link",
        "background": "colors.page_background",
        "accent_color": "colors.accent",
        "line_spacing": "spacing.line_spacing",
        "space_before": "spacing.space_before",
        "space_after": "spacing.space_after",
        "first_line_indent": "spacing.first_line_indent",
        "orientation": "page.orientation",
        "columns": "page.columns",
        "title": "extras.title",
        "subtitle": "extras.subtitle",
        "author": "extras.author",
    }
    for key, path in simple.items():
        if kw.get(key) is not None:
            put(path, kw[key])
    for key, val in _pairs(kw.get("element_font", ()), "--element-font"):
        put(f"fonts.elements.{key}.latin", val)
    for key, val in _pairs(kw.get("element_hebrew_font", ()), "--element-hebrew-font"):
        put(f"fonts.elements.{key}.hebrew", val)
    if kw.get("scale") is not None and kw.get("sizes"):
        raise click.UsageError("Use either --scale or --size, not both.")
    if kw.get("scale") is not None:
        put("sizes.mode", "scale")
        put("sizes.scale", kw["scale"])
    if kw.get("sizes"):
        put("sizes.mode", "exact")
        for key, val in _pairs(kw["sizes"], "--size"):
            if key not in ELEMENT_CHOICES:
                raise click.BadParameter(f"unknown element '{key}'", param_hint="--size")
            put(f"sizes.exact.{key}", float(val))
    custom = []
    if kw.get("heading_color"):
        custom += [(h, kw["heading_color"]) for h in ("h1", "h2", "h3", "h4")]
    custom += _pairs(kw.get("colors", ()), "--color")
    if kw.get("black") and custom:
        raise click.UsageError("--black cannot be combined with --heading-color/--color.")
    if kw.get("black"):
        put("colors.mode", "black")
    elif custom:
        put("colors.mode", "custom")
        for key, val in custom:
            put(f"colors.custom.{key}", val)
    if kw.get("accent_style"):
        put("colors.accent_style", kw["accent_style"])
        if not s.colors.accent:
            put("colors.accent", "#1F3A5F")
    elif kw.get("accent_color") and s.colors.accent_style == "none":
        put("colors.accent_style", "underline")
    if kw.get("strip_bold"):
        put("emphasis.bold", False)
    if kw.get("strip_italic"):
        put("emphasis.italic", False)
    if kw.get("strip_underline"):
        put("emphasis.underline", False)
    if kw.get("bold_to_headings"):
        put("emphasis.bold_lines_to_headings", True)
        put("emphasis.bold_line_heading_level", kw["bold_to_headings"])
    if kw.get("margins"):
        parts = [float(x) for x in str(kw["margins"]).replace(" ", "").split(",") if x]
        if len(parts) == 1:
            parts = parts * 4
        if len(parts) != 4:
            raise click.BadParameter("give one value or four (top,right,bottom,left)", param_hint="--margins")
        for side, v in zip(("top", "right", "bottom", "left"), parts):
            put(f"page.margins.{side}", v)
    if kw.get("page_size"):
        size = str(kw["page_size"]).lower()
        if "x" in size:
            w, h = size.split("x", 1)
            put("page.size", "custom")
            put("page.width_in", float(w))
            put("page.height_in", float(h))
        else:
            put("page.size", size)
    if kw.get("align"):
        put("alignment.mode", kw["align"])
    if kw.get("align_headings"):
        put("alignment.headings", True)
    for flag, path in (
        ("toc", "extras.toc"), ("page_numbers", "extras.page_numbers"), ("title_page", "extras.title_page"),
        ("keep_headers", "extras.keep_headers_footers"), ("keep_page_numbers", "extras.keep_page_numbers"),
        ("strip_nikud", "extras.strip_nikud"), ("strip_teamim", "extras.strip_teamim"),
        ("highlight_uncertain", "extras.highlight_uncertain"),
    ):
        if kw.get(flag):
            put(path, True)
    if kw.get("no_merge_pages"):
        put("extras.merge_across_pages", False)
    if kw.get("no_figures"):
        put("extras.include_figures", False)
    if kw.get("regions"):
        put("extras.regions", kw["regions"].replace("-", "_"))
    for path, val in _pairs(kw.get("sets", ()), "--set"):
        put(path, val)
    return s


STYLE_KEYS = [
    "preset", "body_font", "hebrew_font", "heading_font", "heading_hebrew_font", "element_font", "element_hebrew_font",
    "rashi_font", "scale", "sizes", "black", "heading_color", "colors", "link_color", "background", "accent_color",
    "accent_style", "strip_bold", "strip_italic", "strip_underline", "bold_to_headings", "line_spacing", "space_before",
    "space_after", "first_line_indent", "margins", "page_size", "orientation", "columns", "align", "align_headings",
    "toc", "page_numbers", "title_page", "title", "subtitle", "author", "keep_headers", "keep_page_numbers",
    "no_merge_pages", "strip_nikud", "strip_teamim", "no_figures", "regions", "highlight_uncertain", "sets",
]
READ_KEYS = ["reader", "model", "effort", "languages", "pages", "dpi", "concurrency", "hybrid_threshold", "no_text_layer", "force", "yes", "max_cost"]


def _split(kw: dict, keys: list[str]) -> dict:
    return {k: kw.pop(k) for k in keys if k in kw}


def _formats(spec: str) -> list[str]:
    try:
        return [normalize_format(f) for f in spec.split(",") if f.strip()]
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="--format")


def _settings(r: dict) -> ConvertSettings:
    return ConvertSettings(
        reader=r["reader"], model=r["model"], effort=r["effort"], languages=r["languages"], dpi=r["dpi"],
        concurrency=r["concurrency"], hybrid_threshold=r["hybrid_threshold"], pages=r["pages"],
        use_text_layer=not r["no_text_layer"], force=r["force"],
    )


# ---------------------------------------------------------------- progress & cost


class Progress:
    def __init__(self, label: str = ""):
        self.lock = threading.Lock()
        self.label = label
        self.total = 0
        self.done = 0

    def __call__(self, e: dict) -> None:
        with self.lock:
            t = e["type"]
            if t == "render":
                if e["page"] == 0:
                    click.echo(f"  Preparing {e['total']} page image(s)...")
            elif t == "start":
                self.total = e["total"]
                self.done = self.total - e["todo"]
                if e["todo"] < e["total"]:
                    click.echo(f"  {e['total'] - e['todo']} page(s) already read earlier (cached).")
            elif t == "page_done":
                self.done += 1
                q = f", quality {e['quality']:.0f}%" if e.get("quality") is not None else ""
                c = f", {costs.format_usd(e['cost_usd'])} (total {costs.format_usd(e['total_cost_usd'])})" if e.get("cost_usd") else ""
                click.echo(f"  Page {e['page'] + 1} read [{self.done}/{self.total}] by {e['reader']}{q}{c}")
                if e.get("warning"):
                    click.secho(f"    note: {e['warning']}", fg="yellow")
            elif t == "page_error":
                self.done += 1
                _echo_err(f"  Page {e['page'] + 1} failed: {e['error']}")


def _check_cost(files: list[Path], settings: ConvertSettings, yes: bool, max_cost: Optional[float]) -> None:
    if settings.reader == "local":
        if not tesseract.find_tesseract():
            raise click.ClickException(
                "Tesseract OCR is not installed, so the free local reader cannot run.\n"
                "Install it (see the README, 'Install Tesseract'), or use --reader claude."
            )
        return
    if not config.has_api_key():
        if settings.reader == "claude":
            raise click.ClickException(
                "No Claude API key found. Set ANTHROPIC_API_KEY or put it in a .env file "
                f"(for example {config.home() / '.env'}). Or use --reader local (free)."
            )
        click.secho("No Claude API key found: the hybrid reader will use only the free local reader.", fg="yellow")
        return
    pages = ingest.list_pages(files)
    n = len(ingest.parse_page_range(settings.pages, len(pages)))
    est = costs.estimate_pages(n, settings.model)
    word = "up to " if settings.reader == "hybrid" else ""
    click.echo(
        f"Claude cost estimate for {n} page(s) with {settings.model}: about {word}{costs.format_usd(est['typical'])} "
        f"(range {costs.format_usd(est['low'])}-{costs.format_usd(est['high'])})."
    )
    if max_cost is not None and est["typical"] > max_cost:
        raise click.ClickException(f"The estimate is above --max-cost {max_cost}; nothing was sent.")
    if not yes and sys.stdin.isatty() and est["typical"] >= 0.05:
        click.confirm("Continue?", default=True, abort=True)


def _export_all(project_or_doc, style: StyleOptions, formats: list[str], out_dir: Path, stem: str, root: Optional[Path]) -> list[Path]:
    doc = project_or_doc
    paths = []
    for fmt in formats:
        target = out_dir / f"{stem}{EXTENSIONS[fmt]}"
        try:
            paths.append(export(doc, style, fmt, target, root))
            click.secho(f"  Saved {target}", fg="green")
        except Exception as exc:  # noqa: BLE001 - keep going with the other formats
            _echo_err(f"  Could not save {fmt}: {exc}")
    return paths


def _safe_stem(name: str) -> str:
    keep = "".join(c if c.isalnum() or c in " -_.()[]֐-׿" or "֐" <= c <= "׿" else "_" for c in name)
    return keep.strip() or "document"


# ---------------------------------------------------------------- commands


@click.group(context_settings=CONTEXT)
@click.version_option(__version__, prog_name="scantodoc")
def main() -> None:
    """ScanToDoc turns scanned (image-only) PDFs and page images into editable,
    well-formatted documents: Word, PDF, HTML, Markdown, text.

    Pages are read for free on your computer with Tesseract (--reader local),
    or with Claude for the best quality (--reader claude / hybrid).
    Styles can be changed later with `scantodoc restyle` without reading again.
    """


@main.command("convert", context_settings=CONTEXT)
@click.argument("inputs", nargs=-1, required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--name", default=None, help="Name for the project and output files (default: the first input's name).")
@click.option("--projects-dir", type=click.Path(path_type=Path), default=None,
              help="Where the project folder is kept (default: ~/ScanToDoc/projects).")
@output_options
@reading_options
@style_options
def convert_cmd(inputs, name, projects_dir, formats, out, **kw):
    """Convert scanned PDFs or page images (PNG/JPG/TIFF), or a folder of them,
    into ONE document.

    \b
    Examples:
      scantodoc convert book.pdf
      scantodoc convert book.pdf --format docx,md --preset "Classic sefer"
      scantodoc convert book.pdf --reader claude --body-font "Times New Roman" \\
          --hebrew-font "Frank Ruehl CLM" --heading-color "#1F3A5F" --scale 110 --keep-headers
      scantodoc convert page1.jpg page2.jpg --name "Letter" -f pdf
    """
    r = _split(kw, READ_KEYS)
    style = build_style(**_split(kw, STYLE_KEYS))
    fmts = _formats(formats)
    files = ingest.collect_inputs(inputs)
    if not files:
        raise click.ClickException("No PDF or image files found.")
    settings = _settings(r)
    _check_cost(files, settings, r["yes"], r["max_cost"])
    name = name or files[0].stem
    out_dir = out or files[0].parent
    click.echo(f"Converting {len(files)} file(s) as '{name}' with the {settings.reader} reader...")
    project = Project.create(name, files, parent=projects_dir, settings=settings.to_dict())
    doc = convert(project, settings, Progress())
    project.save_style(style)
    click.echo(f"Project saved in {project.root}")
    _export_all(doc, style, fmts, Path(out_dir), _safe_stem(name), project.root)
    _summary(doc)



def _summary(doc) -> None:
    failed = [p.index + 1 for p in doc.pages if p.status == "error"]
    unsure = sum(1 for _, b in doc.iter_blocks() for r in b.runs if r.uncertain)
    msg = f"Done: {len(doc.pages)} page(s)"
    if doc.usage.cost_usd:
        msg += f", Claude cost {costs.format_usd(doc.usage.cost_usd)}"
    if unsure:
        msg += f", {unsure} uncertain word group(s) worth proofreading"
    click.echo(msg + ".")
    if failed:
        _echo_err(f"Pages that could not be read: {', '.join(map(str, failed))}")


@main.command(context_settings=CONTEXT)
@click.argument("source", type=click.Path(exists=True, path_type=Path))
@output_options
@style_options
@click.option("--no-save", is_flag=True, help="Do not remember this style in the project.")
def restyle(source, formats, out, no_save, **kw):
    """Export again with different styling - no pages are read again, so it is
    instant and free. SOURCE is a project folder, its project.json /
    document.json, or an exported .scantodoc.json file.

    \b
    Examples:
      scantodoc restyle my-book.scantodoc.json --preset "Clean modern" --format pdf
      scantodoc restyle ~/ScanToDoc/projects/my-book --body-font Garamond -f docx,html
    """
    style_kw = _split(kw, STYLE_KEYS)
    fmts = _formats(formats)
    project = None
    if source.is_dir() or source.name in ("project.json", "document.json", "style.json"):
        project = Project.open(source)
        doc = project.load_document()
        if doc is None:
            raise click.ClickException("This project has not been converted yet.")
        style = build_style(project.load_style(), **style_kw)
        stem, root = _safe_stem(project.name), project.root
        out_dir = out or (project.root / "exports")
    else:
        try:
            doc, base = load_bundle(source)
        except Exception as exc:  # noqa: BLE001
            raise click.ClickException(f"{source} is not a ScanToDoc document: {exc}")
        style = build_style(base, **style_kw)
        stem = source.name.replace(".scantodoc.json", "").replace(".json", "")
        root = None
        out_dir = out or source.parent
    click.echo(f"Re-styling '{stem}' ({len(doc.pages)} page(s))...")
    _export_all(doc, style, fmts, Path(out_dir), stem, root)
    if project is not None and not no_save:
        project.save_style(style)


@main.command(context_settings=CONTEXT)
@click.argument("folder", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--recursive", "-r", is_flag=True, help="Also convert files in sub-folders.")
@click.option("--projects-dir", type=click.Path(path_type=Path), default=None, help="Where project folders are kept.")
@output_options
@reading_options
@style_options
def batch(folder, recursive, projects_dir, formats, out, **kw):
    """Convert every PDF (and image) in a folder, each into its own document.

    \b
    Example:
      scantodoc batch ./scans --format docx
      scantodoc batch ./scans -r --reader hybrid --yes -o ./converted
    """
    r = _split(kw, READ_KEYS)
    style = build_style(**_split(kw, STYLE_KEYS))
    fmts = _formats(formats)
    pattern = "**/*" if recursive else "*"
    files = sorted(
        (p for p in folder.glob(pattern) if p.is_file() and p.suffix.lower() in ingest.PDF_EXT | ingest.IMAGE_EXT),
        key=ingest.natural_key,
    )
    if not files:
        raise click.ClickException(f"No PDF or image files in {folder}.")
    settings = _settings(r)
    _check_cost(files, settings, r["yes"], r["max_cost"])
    out_dir = out or (folder / "scantodoc-output")
    ok = failed = 0
    for i, f in enumerate(files, 1):
        click.secho(f"[{i}/{len(files)}] {f.name}", bold=True)
        try:
            project = Project.create(f.stem, [f], parent=projects_dir, settings=settings.to_dict())
            doc = convert(project, settings, Progress())
            project.save_style(style)
            target = out_dir / f.relative_to(folder).parent if recursive else out_dir
            _export_all(doc, style, fmts, target, _safe_stem(f.stem), project.root)
            ok += 1
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop the batch
            failed += 1
            _echo_err(f"  {f.name} failed: {exc}")
    click.echo(f"Batch finished: {ok} converted, {failed} failed. Output in {out_dir}")


@main.command(context_settings=CONTEXT)
@click.argument("inputs", nargs=-1, required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--model", default=costs.DEFAULT_MODEL, show_default=True, help="Claude model to price.")
@click.option("--pages", default=None, help="Only these pages, e.g. '1-10'.")
def estimate(inputs, model, pages):
    """Show what reading these files with Claude would cost (nothing is sent)."""
    files = ingest.collect_inputs(inputs)
    all_pages = ingest.list_pages(files)
    n = len(ingest.parse_page_range(pages, len(all_pages)))
    click.echo(f"{n} page(s). The local reader is free.")
    for m in costs.PRICES:
        est = costs.estimate_pages(n, m)
        mark = " <- chosen" if m == model else ""
        click.echo(
            f"  {m:20s} about {costs.format_usd(est['typical']):>9s}  (range {costs.format_usd(est['low'])}-"
            f"{costs.format_usd(est['high'])}){mark}"
        )
    click.echo("Estimates assume a typical book page; dense pages (small print, commentaries) cost more.")


@main.command(context_settings=CONTEXT)
@click.option("--host", default="127.0.0.1", show_default=True, help="Address to listen on (127.0.0.1 = only this computer).")
@click.option("--port", default=8765, show_default=True, type=int, help="Port for the web app.")
@click.option("--no-browser", is_flag=True, help="Do not open the web browser automatically.")
def serve(host, port, no_browser):
    """Start the ScanToDoc web app (then open http://localhost:8765)."""
    import uvicorn

    from .web.app import create_app

    url = f"http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}"
    click.secho(f"ScanToDoc is running at {url}  (press Ctrl+C to stop)", fg="green", bold=True)
    if not no_browser:
        threading.Timer(1.2, lambda: _open_browser(url)).start()
    local = host in ("127.0.0.1", "localhost", "::1")
    uvicorn.run(create_app(local_only=local), host=host, port=port, log_level="warning")


def _open_browser(url: str) -> None:
    import webbrowser

    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        pass


@main.group(context_settings=CONTEXT)
def preset():
    """List, show, save and delete style presets."""


@preset.command("list")
def preset_list():
    """List the built-in and saved presets."""
    for p in presets.list_presets():
        tag = "built-in" if p["builtin"] else "saved"
        click.echo(f"  {p['name']:24s} [{tag}] {p['description']}")


@preset.command("show")
@click.argument("name")
def preset_show(name):
    """Print a preset's full settings as JSON."""
    try:
        click.echo(presets.load(name).model_dump_json(indent=2))
    except KeyError as exc:
        raise click.ClickException(exc.args[0])


@preset.command("save", context_settings=CONTEXT)
@click.argument("name")
@click.option("--description", default="", help="A short description shown in lists.")
@style_options
def preset_save(name, description, **kw):
    """Save the given style options as a named preset.

    \b
    Example:
      scantodoc preset save "My navy" --preset "Clean modern" --heading-color "#1F3A5F"
    """
    style = build_style(**_split(kw, STYLE_KEYS))
    path = presets.save(style, name, description)
    click.secho(f"Saved preset '{name}' to {path}", fg="green")


@preset.command("delete")
@click.argument("name")
def preset_delete(name):
    """Delete a saved preset (built-in presets cannot be deleted)."""
    if presets.delete(name):
        click.echo(f"Deleted '{name}'.")
    else:
        raise click.ClickException(f"No saved preset called '{name}'.")


@main.command("presets", hidden=True)
@click.pass_context
def presets_alias(ctx):
    """Same as `preset list`."""
    ctx.invoke(preset_list)


@main.group(context_settings=CONTEXT, invoke_without_command=True)
@click.option("--hebrew", is_flag=True, help="Only Hebrew-script fonts.")
@click.option("--latin", is_flag=True, help="Only Latin-script fonts.")
@click.pass_context
def fonts(ctx, hebrew, latin):
    """List the curated fonts (any other installed font name also works)."""
    if ctx.invoked_subcommand:
        return
    for f in font_list.curated():
        if hebrew and f["script"] == "latin" or latin and f["script"] == "hebrew":
            continue
        click.echo(f"  {f['name']:22s} {f['script']:7s} {f['category']:11s} {f['source']}")
    click.echo("Bundled fonts are always used in HTML/PDF. For Word, run `scantodoc fonts install` once.")


@fonts.command("install")
def fonts_install():
    """Install ScanToDoc's bundled free fonts (Frank Ruhl Libre, David Libre,
    Noto Rashi Hebrew, ...) for your user, so Word can show them too."""
    from .fontinstall import install_bundled

    for line in install_bundled():
        click.echo(line)


@main.command(context_settings=CONTEXT)
@click.option("--json", "as_json", is_flag=True, help="Print as JSON.")
def projects(as_json):
    """List past conversions (projects)."""
    items = [p.summary() | {"path": str(p.root)} for p in list_projects()]
    if as_json:
        click.echo(json.dumps(items, indent=2, ensure_ascii=False))
        return
    if not items:
        click.echo("No projects yet.")
    for it in items:
        click.echo(f"  {it['name'][:40]:40s} {it['page_count']:4d} pages  {it['status']:10s} {it['path']}")


@main.command(context_settings=CONTEXT)
def doctor():
    """Check that everything ScanToDoc needs is installed, and explain what is missing."""
    from . import browser

    ok = True

    def line(good: bool, text: str, fix: str = "") -> None:
        nonlocal ok
        ok = ok and good
        click.secho(("  OK    " if good else "  MISSING ") + text, fg="green" if good else "yellow")
        if fix and not good:
            click.echo("        " + fix)

    click.echo(f"ScanToDoc {__version__}, Python {sys.version.split()[0]}")
    exe = tesseract.find_tesseract()
    line(bool(exe), f"Tesseract OCR {tesseract.version() if exe else ''} {exe or ''}",
         "Needed for the free local reader. Windows: install from https://github.com/UB-Mannheim/tesseract/wiki ; "
         "Mac: brew install tesseract tesseract-lang")
    if exe:
        langs = set(tesseract.languages())
        for code, name in (("eng", "English"), ("heb", "Hebrew"), ("yid", "Yiddish (optional)")):
            line(code in langs, f"Tesseract language: {name} ({code})",
                 "Install the language data (Mac: brew install tesseract-lang; Windows: tick it in the installer).")
    line(browser.available(), "Chromium/Chrome/Edge for PDF export", "Run: python -m playwright install chromium")
    line(config.has_api_key(), "Claude API key (only needed for the claude/hybrid readers)",
         f"Set ANTHROPIC_API_KEY, or add ANTHROPIC_API_KEY=... to {config.home() / '.env'}")
    click.echo(f"  Projects folder: {config.projects_dir()}")
    click.echo("All set." if ok else "Some optional parts are missing (see above).")


if __name__ == "__main__":  # pragma: no cover
    main()
