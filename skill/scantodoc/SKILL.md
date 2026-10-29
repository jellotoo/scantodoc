---
name: scantodoc
description: Turn scanned (image-only) PDFs, photos of pages or folders of page images into editable, well-formatted documents (Word .docx, PDF with real text, HTML, Markdown, plain text), keeping headings, bold/italic, tables with merged cells, footnotes, pictures and layout, with full Hebrew, Yiddish and Aramaic right-to-left support (including Gemara-style pages with Rashi and Tosafot). Use when the user wants to OCR a scan, "make this PDF editable", convert a scanned book/sefer/letter/article to Word or another format, restyle a converted document (fonts, sizes, colours, spacing, table of contents, page numbers), or batch-convert a folder of scans.
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/run.py *) Bash(python ${CLAUDE_SKILL_DIR}/scripts/run.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/setup.py *) Bash(python ${CLAUDE_SKILL_DIR}/scripts/setup.py *)
---

# ScanToDoc

ScanToDoc reads each page of a scan, builds a document model (headings, paragraphs, lists,
tables, figures, footnotes, regions) and exports it with real Word heading styles and
proper right-to-left text. Styling is applied at export time, so a document can be restyled
any number of times without reading the pages again.

`<skill>` below means this skill's folder (in Claude Code: `${CLAUDE_SKILL_DIR}`). Run every
command through `python3 <skill>/scripts/run.py ...`. On Windows use `python` instead of
`python3`. The first run installs ScanToDoc into its own environment (`~/ScanToDoc/venv`),
which takes a few minutes and needs internet access to pypi.org. Run
`run.py doctor` to see what is available here.

## 1. Pick how the pages are read

| Reader | How | Cost | When |
|---|---|---|---|
| **in the chat** | `prepare` → you read each page image → `assemble` | no API key; uses the conversation | Best quality without a key. Default when Tesseract is missing (for example in the Claude app), and for Hebrew, Gemara layouts or tables. Practical up to ~30 pages |
| `--reader local` | Tesseract OCR on this computer | free, offline | Default when `doctor` shows Tesseract. Good for clean printed text |
| `--reader hybrid` | local first, Claude API only for weak pages | small | Long books with some hard pages; needs `ANTHROPIC_API_KEY` |
| `--reader claude` | Claude API for every page | estimated ¼¢ a page with the default Haiku model, about 5¢ with Sonnet, 10¢ with Opus (`--model`) | Long books, best quality, needs `ANTHROPIC_API_KEY` |

Follow the user's choice if they made one. Before an API reader, show the cost first with
`run.py estimate FILE` and get the user's agreement. Never ask the user to paste an API key
into the chat. They set `ANTHROPIC_API_KEY` themselves, or save it in `~/ScanToDoc/.env`
(the web app's Settings does this).

Reading in the chat also works as a fix-up. After a local conversion, the output lists each
page's quality. Hand only the weak pages over with `run.py prepare <project> --pages 3,7`,
write those page files, then run `assemble`. The other pages stay as they were.

## 2a. Read in the chat (no API key)

1. `python3 <skill>/scripts/run.py prepare scan.pdf` (add `--pages 1-10` for part of it,
   `--name "My book"` for a name). It prints the project folder and, for each page, the
   image to look at and the JSON file to write. `--json` prints the same as JSON.
2. Read `<skill>/reference/page-format.md` once (the page format and reading rules).
3. For each page, open the image with your file-viewing tool (Claude Code: Read). Read the
   page carefully and write its JSON file. For small print, footnotes or commentary, make a
   close-up first with `run.py zoom IMAGE x0,y0,x1,y1` (0-1000 scale) and look at that.
   If `pages.json` lists a `text_layer` file for a page, read it too: its spelling is
   reliable, but its order and formatting are not.
4. `run.py assemble <project> --check` reports exactly what is wrong in any page file. Fix
   the files and check again.
5. `run.py assemble <project> -f docx` (plus any style options, see below) builds and
   exports the document.

In Claude Code, for long documents, you may give batches of pages to subagents. Each one
writes its own page files and follows page-format.md. Then run `assemble` once.

## 2b. Read on this computer or with the API

```
python3 <skill>/scripts/run.py convert scan.pdf -f docx
python3 <skill>/scripts/run.py convert scan.pdf --reader hybrid -y -f docx,pdf
python3 <skill>/scripts/run.py batch ./scans -r -f docx -o ./converted
```

Hebrew and English are read by default (`--languages eng+heb`). Add `+yid` for Yiddish if
that Tesseract language pack is installed.

## 3. Style and export

Every export command (`convert`, `batch`, `assemble`, `restyle`) accepts the same style
options. Restyling never reads pages again, so it is instant and free:

```
python3 <skill>/scripts/run.py restyle <project> --preset "Classic sefer" -f docx,pdf
```

- **Formats** (`-f`, comma-separated): `docx` (real Heading 1-4 styles), `pdf` (real text;
  needs Chrome, Edge or Chromium), `html`, `md`, `txt`, `json` (the document model, which can
  be restyled later). `-o FOLDER` sets where files go. By default they go next to the input
  (`convert`/`batch`) or in `<project>/exports` (`assemble`/`restyle`).
- **Presets**: `"Keep original"` (the default look of the scan), `"Clean modern"`,
  `"Classic sefer"`, `"Academic"`, or one the user saved (`preset list/show/save/delete`).
  Options given with a preset override it.
- **Fonts**: `--body-font` (Latin), `--hebrew-font`, `--heading-font`,
  `--heading-hebrew-font`, `--element-font h1=Georgia`, `--element-hebrew-font footnote=David`,
  `--rashi-font`. `run.py fonts` lists the curated fonts. Bundled free Hebrew fonts:
  Frank Ruhl Libre, David Libre, Noto Rashi Hebrew, Alef, Heebo and others. Any installed font
  name also works. For Word to show the bundled fonts, run `run.py fonts install` once.
- **Sizes**: `--scale 110` (percent of the detected sizes), `--size body=12,h1=24` (elements:
  body, h1-h4, list, table, caption, footnote, quote).
- **Colours**: `--black`, `--heading-color #1F3A5F`, `--color h2=#884400`, `--link-color`,
  `--background`, `--accent-color` with `--accent-style underline|rule|bar`.
- **Emphasis**: `--strip-bold`, `--strip-italic`, `--strip-underline`,
  `--bold-to-headings LEVEL` (turns short all-bold lines into real headings).
- **Spacing**: `--line-spacing 1.5`, `--space-before PT`, `--space-after PT`,
  `--first-line-indent PT`.
- **Page**: `--page-size letter|a4|legal|a5|6x9`, `--orientation`, `--margins 1` or
  `--margins 1,0.8,1,0.8`, `--columns 1-3`.
- **Alignment**: `--align keep|start|left|right|justify` (`start` means left for English and
  right for Hebrew), `--align-headings`.
- **Extras**: `--toc`, `--page-numbers`, `--title-page` with `--title`, `--subtitle`,
  `--author`.
- **Content**: by default running headers and footers, printed page numbers, and paragraphs
  split by a page break are cleaned up. Undo with `--keep-headers`, `--keep-page-numbers`,
  `--no-merge-pages`. Also available: `--strip-nikud`, `--strip-teamim`, `--no-figures`,
  `--regions per-page|grouped|main-only` (how Gemara-style pages are ordered), and
  `--highlight-uncertain` (marks words the reader was unsure of, for proofreading).
- **Anything else**: `--set PATH=VALUE`, e.g. `--set extras.toc_title=תוכן`.

The full help for every command and option is in `<skill>/reference/options.md`, or run
`run.py COMMAND --help`.

## 4. Other commands

- `run.py serve` starts the web app at http://localhost:8765, on the user's own computer
  only. It shows the scan next to the result, a live style panel, editing in place, and
  downloads. Suggest it when the user wants to proofread or fix text by hand.
- `run.py projects` lists past conversions. Each is a folder in `~/ScanToDoc/projects` that
  can be restyled or opened in the web app.
- `run.py estimate FILE` shows the API cost without sending anything.
- `run.py doctor` checks Tesseract, its languages, a browser for PDF export, and the API key.

## Examples

- "Make this scanned PDF an editable Word file" → run `doctor`. If Tesseract is present,
  `convert scan.pdf -f docx`; otherwise read in the chat (2a). Report the output path and any
  pages that failed or had low quality.
- "Convert my scanned sefer with Rashi to Word, in a classic look" → read in the chat with
  regions, then `assemble <project> --preset "Classic sefer" -f docx`.
- "Same document, but Garamond 12 with a table of contents and page numbers, as PDF" →
  `restyle <project> --body-font "EB Garamond" --size body=12 --toc --page-numbers -f pdf`.
- "Convert every PDF in this folder" → `batch FOLDER -f docx` (add `-r` for subfolders).

## Good to know

- Do not change the content. Reading means copying what is printed; corrections are for the
  user to ask for.
- If PDF export says no browser was found, offer `.docx` or `.html` instead. Word and
  browsers can print to PDF. Or the user can run `python -m playwright install chromium` on
  their computer.
- In the Claude app, save the final files where the app lets the user download them, and
  tell the user their names.
