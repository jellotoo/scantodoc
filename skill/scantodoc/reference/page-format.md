# Writing a page file (reading pages in the chat)

After `run.py prepare`, write one JSON file per page at the `answer` path listed for it
(`<project>/agent/page-0001.json`, ...). The project's `agent/reading-rules.md` has the full
reading rules and `agent/schema.json` the strict schema. Below is the short form that
`assemble` accepts. Any field left out gets the default shown.

## The page

```json
{"regions": [], "blocks": [ ...blocks in reading order... ]}
```

A bare list of blocks is fine too. Every page needs its file, even an empty one (`[]`).

## Blocks

| Field | Default | Meaning |
|---|---|---|
| `type` | required | `heading`, `paragraph`, `list_item`, `table`, `caption`, `footnote`, `quote`, `figure`, `header`, `footer`, `page_number` |
| `text` | — | The block's text, if it has one style throughout (shortcut for `runs`) |
| `runs` | `[]` | Pieces of text with their own style (see below); a plain string is a plain run |
| `heading_level` | 1 for headings | 1 (biggest) to 4. Headings that look alike get the same level |
| `list_marker` | `""` | The printed bullet or number (`"•"`, `"3."`, `"(ב)"`); do not repeat it in the text |
| `list_level` | 0 | Nesting depth of list items |
| `alignment` | `left`, or `right` for Hebrew | `left`, `center`, `right`, `justify` |
| `direction` | from the letters | `rtl` for Hebrew/Yiddish/Aramaic, `ltr` otherwise |
| `indent_level` | 0 | Whole-block indent: 1 = about half an inch |
| `first_line_indent` | false | Only the first line is indented |
| `font_size_pt` | none | Estimated type size in points (the page's size in inches is in `pages.json`) |
| `font_category` | `serif` | `serif`, `sans-serif`, `monospace`, `script`, `rashi` |
| `box` | none | `[x0, y0, x1, y1]` on a 0-1000 scale of the page image (0,0 = top-left). **Needed for figures** (the picture is cut out of the scan from it). It also draws the outline in the web app |
| `continues_on_next_page` | false | The page's last paragraph stops mid-sentence |
| `continues_from_previous_page` | false | The page's first paragraph starts mid-sentence (the two halves are joined) |
| `region` | `""` | Region id, on multi-region pages only |
| `table_rows` | `[]` | Tables only, see below |
| `figure_description` | `""` | Figures only: a short description of the picture |

Running heads, footers and printed page numbers are dropped from the output by default, but
mark them with their types anyway (`header`, `footer`, `page_number`) so that the user can
choose to keep them.

## Runs (formatting inside a block)

```json
{"text": "important", "bold": true, "italic": false, "underline": false, "strikethrough": false,
 "superscript": false, "subscript": false, "color": "", "uncertain": false}
```

Start a new run wherever the formatting changes. Give only the fields that are true.
`color` is `"#RRGGBB"` for clearly coloured text. Set `"uncertain": true` on a run holding
just a word you could not read with confidence; it gets highlighted for proofreading.

## Tables

```json
{"type": "table", "table_rows": [
  [{"text": "Name", "is_header": true}, {"text": "Year", "is_header": true}],
  ["Gutenberg", "1450"],
  [{"text": "Merged across both columns", "colspan": 2}]
]}
```

A row is a list of cells or `{"cells": [...]}`. A cell is a string, or an object with
`text`/`runs`, `colspan`, `rowspan` (1 unless merged) and `is_header`.

## Figures

```json
{"type": "figure", "box": [120, 410, 880, 700], "figure_description": "Engraving of a printing press"}
```

Text printed inside a picture belongs to the figure. A caption under it is its own `caption`
block.

## Pages with several texts (Gemara, commentaries, side notes)

```json
{"regions": [
   {"id": "main", "label": "Main text", "kind": "main"},
   {"id": "rashi", "label": "Rashi", "kind": "commentary", "font_category": "rashi"},
   {"id": "tosafot", "label": "Tosafot", "kind": "commentary", "font_category": "rashi"}],
 "blocks": [
   {"type": "paragraph", "region": "main", "text": "..."},
   {"type": "paragraph", "region": "rashi", "font_category": "rashi", "text": "..."}
 ]}
```

Give the blocks region by region (main text first), each region in its own reading order.
`kind` is `main`, `commentary`, `sidebar`, `column` or `other`.

## Reading rules (short version)

- Copy exactly what is printed: spelling, punctuation and numbers. Never correct, modernise,
  translate, summarise or complete text.
- Hebrew, Yiddish and Aramaic go in reading (logical) order. Never reverse letters or words.
- Keep nikud and ta'amim only where printed.
- Join the lines of a paragraph with single spaces. Remove a hyphen that only splits an English
  word at a line end. Keep real hyphens and the maqaf (־).
- Small print is hard to read in a downsized image. Use `run.py zoom IMAGE x0,y0,x1,y1` to get
  a full-resolution close-up of part of the page, then look at that file.
