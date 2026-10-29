# ScanToDoc command reference

Generated from `scantodoc COMMAND --help` by `skill/build.py`; do not edit by hand.
Run commands through `scripts/run.py`, e.g. `python3 scripts/run.py convert book.pdf`.

## convert

```text
Usage: scantodoc convert [OPTIONS] INPUTS...

  Convert scanned PDFs or page images (PNG/JPG/TIFF), or a folder of them, into ONE document.

  Examples:
    scantodoc convert book.pdf
    scantodoc convert book.pdf --format docx,md --preset "Classic sefer"
    scantodoc convert book.pdf --reader claude --body-font "Times New Roman" \
        --hebrew-font "Frank Ruehl CLM" --heading-color "#1F3A5F" --scale 110 --keep-headers
    scantodoc convert page1.jpg page2.jpg --name "Letter" -f pdf

Options:
  --name TEXT                     Name for the project and output files (default: the first input's
                                  name).
  --projects-dir PATH             Where the project folder is kept (default: ~/ScanToDoc/projects).
  -f, --format TEXT               Comma-separated export formats: docx, pdf, html, md, txt, json.
                                  [default: docx]
  -o, --out PATH                  Folder for the exported files (default: next to the input).
  --reader [local|claude|hybrid]  How pages are read. local = free Tesseract OCR on this computer
                                  (no internet); claude = Claude AI (best quality, costs money,
                                  needs ANTHROPIC_API_KEY); hybrid = local first, Claude only for
                                  pages the local reader struggles with.  [default: local]
  --model TEXT                    Claude model for the claude/hybrid readers: claude-haiku-5-5
                                  (cheapest), claude-sonnet-5-5, or claude-opus-5-5 (most accurate).
                                  [default: claude-haiku-5-5]
  --effort [low|medium|high|xhigh|max]
                                  How hard Claude thinks about each page. Higher costs more.
                                  [default: medium]
  --languages TEXT                Tesseract languages for the local reader, joined with '+'. Add
                                  'yid' for Yiddish (needs the Yiddish language pack).  [default:
                                  eng+heb]
  --pages TEXT                    Only these pages, e.g. '1-10,15' (counting from 1).
  --dpi INTEGER                   Resolution for page images.  [default: 300]
  --concurrency INTEGER           Pages read at the same time.  [default: 4]
  --hybrid-threshold FLOAT        Hybrid reader: pages whose local reading scores below this (0-100)
                                  go to Claude.  [default: 85.0]
  --no-text-layer                 Ignore text already inside the PDF and read the images.
  --force                         Read pages again even if they were read before (uses the API
                                  again).
  -y, --yes                       Do not ask before spending money on Claude.
  --max-cost FLOAT                Stop before starting if the estimated Claude cost (US$) is above
                                  this.
  --preset TEXT                   A style preset name ("Keep original", "Clean modern", "Classic
                                  sefer", "Academic", or one you saved) or a preset .json file.
                                  Other style options are applied on top.
  --body-font TEXT                Font for all Latin-script text (e.g. 'Times New Roman',
                                  'Garamond').
  --hebrew-font TEXT              Font for all Hebrew/Yiddish/Aramaic text (e.g. 'Frank Ruehl CLM',
                                  'David').
  --heading-font TEXT             Latin font for all headings.
  --heading-hebrew-font TEXT      Hebrew font for all headings.
  --element-font ELEMENT=FONT     Latin font for one element: h1, h2, h3, h4, list, table, caption,
                                  footnote or quote. Repeat as needed, e.g. --element-font
                                  h1=Georgia.
  --element-hebrew-font ELEMENT=FONT
                                  Hebrew font for one element, e.g. --element-hebrew-font
                                  footnote=David.
  --rashi-font TEXT               Font for text detected in Rashi script (default: Noto Rashi
                                  Hebrew).
  --scale FLOAT                   Scale every detected size, in percent (e.g. 110).
  --size ELEMENT=PT               Exact size in points for an element (body, h1-h4, list, table,
                                  caption, footnote, quote). Repeatable or comma-separated: --size
                                  body=12,h1=24. Elements not given keep their detected size.
  --black                         Make all text black (ignore detected colours).
  --heading-color #RRGGBB         Colour for all headings.
  --color ELEMENT=#RRGGBB         Colour for one element: body, h1-h4, list, quote, caption,
                                  footnote. Repeatable.
  --link-color #RRGGBB            Colour for web links.
  --background #RRGGBB            Page background colour.
  --accent-color #RRGGBB          Colour of a line under or beside headings.
  --accent-style [underline|rule|bar]
                                  Heading accent: underline (thick line below), rule (thin line
                                  below) or bar (beside).
  --strip-bold                    Remove bold from the text (headings keep their heading look).
  --strip-italic                  Remove italic.
  --strip-underline               Remove underline.
  --bold-to-headings LEVEL        Turn short lines that are entirely bold into real headings of this
                                  level (1-4).  [1<=x<=4]
  --line-spacing FLOAT            Line spacing as a multiple (1 = single, 1.5, 2 = double).
  --space-before FLOAT            Space before each paragraph, in points.
  --space-after FLOAT             Space after each paragraph, in points.
  --first-line-indent FLOAT       First-line indent of paragraphs, in points (0 = none).
  --margins INCHES                Page margins in inches: one value for all sides, or
                                  top,right,bottom,left.
  --page-size SIZE                letter, a4, legal, a5, or WIDTHxHEIGHT in inches (e.g. 6x9).
                                  Default: like the scan.
  --orientation [portrait|landscape]
                                  Page orientation.
  --columns INTEGER RANGE         Text columns per page (1-3).  [1<=x<=3]
  --align [keep|start|left|right|justify]
                                  Paragraph alignment. start = left for English, right for Hebrew.
                                  keep = as scanned.
  --align-headings                Also apply --align to headings (normally they keep theirs).
  --toc                           Add a table of contents built from the headings.
  --page-numbers                  Add page numbers in the footer.
  --title-page                    Add a title page (see --title, --subtitle, --author).
  --title TEXT                    Document title (title page and file properties).
  --subtitle TEXT                 Subtitle for the title page.
  --author TEXT                   Author for the title page and file properties.
  --keep-headers                  Keep the running headers and footers printed on the scanned pages.
  --keep-page-numbers             Keep the scan's own printed page numbers.
  --no-merge-pages                Do not join paragraphs that a page break split in two.
  --strip-nikud                   Remove Hebrew vowel points (nikud).
  --strip-teamim                  Remove cantillation marks (ta'amim).
  --no-figures                    Leave out pictures cropped from the pages.
  --regions [per-page|grouped|main-only]
                                  Pages with several texts (e.g. Gemara with Rashi): per-page = main
                                  text then each commentary, page by page; grouped = all main text,
                                  then each commentary; main-only.
  --highlight-uncertain           Highlight words the reader was unsure of (for proofreading).
  --set PATH=VALUE                Set any style option by its path, e.g. --set
                                  extras.toc_title=Inhalt. Repeatable.
  -h, --help                      Show this message and exit.
```

## restyle

```text
Usage: scantodoc restyle [OPTIONS] SOURCE

  Export again with different styling - no pages are read again, so it is instant and free. SOURCE
  is a project folder, its project.json / document.json, or an exported .scantodoc.json file.

  Examples:
    scantodoc restyle my-book.scantodoc.json --preset "Clean modern" --format pdf
    scantodoc restyle ~/ScanToDoc/projects/my-book --body-font Garamond -f docx,html

Options:
  -f, --format TEXT               Comma-separated export formats: docx, pdf, html, md, txt, json.
                                  [default: docx]
  -o, --out PATH                  Folder for the exported files (default: next to the input).
  --preset TEXT                   A style preset name ("Keep original", "Clean modern", "Classic
                                  sefer", "Academic", or one you saved) or a preset .json file.
                                  Other style options are applied on top.
  --body-font TEXT                Font for all Latin-script text (e.g. 'Times New Roman',
                                  'Garamond').
  --hebrew-font TEXT              Font for all Hebrew/Yiddish/Aramaic text (e.g. 'Frank Ruehl CLM',
                                  'David').
  --heading-font TEXT             Latin font for all headings.
  --heading-hebrew-font TEXT      Hebrew font for all headings.
  --element-font ELEMENT=FONT     Latin font for one element: h1, h2, h3, h4, list, table, caption,
                                  footnote or quote. Repeat as needed, e.g. --element-font
                                  h1=Georgia.
  --element-hebrew-font ELEMENT=FONT
                                  Hebrew font for one element, e.g. --element-hebrew-font
                                  footnote=David.
  --rashi-font TEXT               Font for text detected in Rashi script (default: Noto Rashi
                                  Hebrew).
  --scale FLOAT                   Scale every detected size, in percent (e.g. 110).
  --size ELEMENT=PT               Exact size in points for an element (body, h1-h4, list, table,
                                  caption, footnote, quote). Repeatable or comma-separated: --size
                                  body=12,h1=24. Elements not given keep their detected size.
  --black                         Make all text black (ignore detected colours).
  --heading-color #RRGGBB         Colour for all headings.
  --color ELEMENT=#RRGGBB         Colour for one element: body, h1-h4, list, quote, caption,
                                  footnote. Repeatable.
  --link-color #RRGGBB            Colour for web links.
  --background #RRGGBB            Page background colour.
  --accent-color #RRGGBB          Colour of a line under or beside headings.
  --accent-style [underline|rule|bar]
                                  Heading accent: underline (thick line below), rule (thin line
                                  below) or bar (beside).
  --strip-bold                    Remove bold from the text (headings keep their heading look).
  --strip-italic                  Remove italic.
  --strip-underline               Remove underline.
  --bold-to-headings LEVEL        Turn short lines that are entirely bold into real headings of this
                                  level (1-4).  [1<=x<=4]
  --line-spacing FLOAT            Line spacing as a multiple (1 = single, 1.5, 2 = double).
  --space-before FLOAT            Space before each paragraph, in points.
  --space-after FLOAT             Space after each paragraph, in points.
  --first-line-indent FLOAT       First-line indent of paragraphs, in points (0 = none).
  --margins INCHES                Page margins in inches: one value for all sides, or
                                  top,right,bottom,left.
  --page-size SIZE                letter, a4, legal, a5, or WIDTHxHEIGHT in inches (e.g. 6x9).
                                  Default: like the scan.
  --orientation [portrait|landscape]
                                  Page orientation.
  --columns INTEGER RANGE         Text columns per page (1-3).  [1<=x<=3]
  --align [keep|start|left|right|justify]
                                  Paragraph alignment. start = left for English, right for Hebrew.
                                  keep = as scanned.
  --align-headings                Also apply --align to headings (normally they keep theirs).
  --toc                           Add a table of contents built from the headings.
  --page-numbers                  Add page numbers in the footer.
  --title-page                    Add a title page (see --title, --subtitle, --author).
  --title TEXT                    Document title (title page and file properties).
  --subtitle TEXT                 Subtitle for the title page.
  --author TEXT                   Author for the title page and file properties.
  --keep-headers                  Keep the running headers and footers printed on the scanned pages.
  --keep-page-numbers             Keep the scan's own printed page numbers.
  --no-merge-pages                Do not join paragraphs that a page break split in two.
  --strip-nikud                   Remove Hebrew vowel points (nikud).
  --strip-teamim                  Remove cantillation marks (ta'amim).
  --no-figures                    Leave out pictures cropped from the pages.
  --regions [per-page|grouped|main-only]
                                  Pages with several texts (e.g. Gemara with Rashi): per-page = main
                                  text then each commentary, page by page; grouped = all main text,
                                  then each commentary; main-only.
  --highlight-uncertain           Highlight words the reader was unsure of (for proofreading).
  --set PATH=VALUE                Set any style option by its path, e.g. --set
                                  extras.toc_title=Inhalt. Repeatable.
  --no-save                       Do not remember this style in the project.
  -h, --help                      Show this message and exit.
```

## batch

```text
Usage: scantodoc batch [OPTIONS] FOLDER

  Convert every PDF (and image) in a folder, each into its own document.

  Example:
    scantodoc batch ./scans --format docx
    scantodoc batch ./scans -r --reader hybrid --yes -o ./converted

Options:
  -r, --recursive                 Also convert files in sub-folders.
  --projects-dir PATH             Where project folders are kept.
  -f, --format TEXT               Comma-separated export formats: docx, pdf, html, md, txt, json.
                                  [default: docx]
  -o, --out PATH                  Folder for the exported files (default: next to the input).
  --reader [local|claude|hybrid]  How pages are read. local = free Tesseract OCR on this computer
                                  (no internet); claude = Claude AI (best quality, costs money,
                                  needs ANTHROPIC_API_KEY); hybrid = local first, Claude only for
                                  pages the local reader struggles with.  [default: local]
  --model TEXT                    Claude model for the claude/hybrid readers: claude-haiku-5-5
                                  (cheapest), claude-sonnet-5-5, or claude-opus-5-5 (most accurate).
                                  [default: claude-haiku-5-5]
  --effort [low|medium|high|xhigh|max]
                                  How hard Claude thinks about each page. Higher costs more.
                                  [default: medium]
  --languages TEXT                Tesseract languages for the local reader, joined with '+'. Add
                                  'yid' for Yiddish (needs the Yiddish language pack).  [default:
                                  eng+heb]
  --pages TEXT                    Only these pages, e.g. '1-10,15' (counting from 1).
  --dpi INTEGER                   Resolution for page images.  [default: 300]
  --concurrency INTEGER           Pages read at the same time.  [default: 4]
  --hybrid-threshold FLOAT        Hybrid reader: pages whose local reading scores below this (0-100)
                                  go to Claude.  [default: 85.0]
  --no-text-layer                 Ignore text already inside the PDF and read the images.
  --force                         Read pages again even if they were read before (uses the API
                                  again).
  -y, --yes                       Do not ask before spending money on Claude.
  --max-cost FLOAT                Stop before starting if the estimated Claude cost (US$) is above
                                  this.
  --preset TEXT                   A style preset name ("Keep original", "Clean modern", "Classic
                                  sefer", "Academic", or one you saved) or a preset .json file.
                                  Other style options are applied on top.
  --body-font TEXT                Font for all Latin-script text (e.g. 'Times New Roman',
                                  'Garamond').
  --hebrew-font TEXT              Font for all Hebrew/Yiddish/Aramaic text (e.g. 'Frank Ruehl CLM',
                                  'David').
  --heading-font TEXT             Latin font for all headings.
  --heading-hebrew-font TEXT      Hebrew font for all headings.
  --element-font ELEMENT=FONT     Latin font for one element: h1, h2, h3, h4, list, table, caption,
                                  footnote or quote. Repeat as needed, e.g. --element-font
                                  h1=Georgia.
  --element-hebrew-font ELEMENT=FONT
                                  Hebrew font for one element, e.g. --element-hebrew-font
                                  footnote=David.
  --rashi-font TEXT               Font for text detected in Rashi script (default: Noto Rashi
                                  Hebrew).
  --scale FLOAT                   Scale every detected size, in percent (e.g. 110).
  --size ELEMENT=PT               Exact size in points for an element (body, h1-h4, list, table,
                                  caption, footnote, quote). Repeatable or comma-separated: --size
                                  body=12,h1=24. Elements not given keep their detected size.
  --black                         Make all text black (ignore detected colours).
  --heading-color #RRGGBB         Colour for all headings.
  --color ELEMENT=#RRGGBB         Colour for one element: body, h1-h4, list, quote, caption,
                                  footnote. Repeatable.
  --link-color #RRGGBB            Colour for web links.
  --background #RRGGBB            Page background colour.
  --accent-color #RRGGBB          Colour of a line under or beside headings.
  --accent-style [underline|rule|bar]
                                  Heading accent: underline (thick line below), rule (thin line
                                  below) or bar (beside).
  --strip-bold                    Remove bold from the text (headings keep their heading look).
  --strip-italic                  Remove italic.
  --strip-underline               Remove underline.
  --bold-to-headings LEVEL        Turn short lines that are entirely bold into real headings of this
                                  level (1-4).  [1<=x<=4]
  --line-spacing FLOAT            Line spacing as a multiple (1 = single, 1.5, 2 = double).
  --space-before FLOAT            Space before each paragraph, in points.
  --space-after FLOAT             Space after each paragraph, in points.
  --first-line-indent FLOAT       First-line indent of paragraphs, in points (0 = none).
  --margins INCHES                Page margins in inches: one value for all sides, or
                                  top,right,bottom,left.
  --page-size SIZE                letter, a4, legal, a5, or WIDTHxHEIGHT in inches (e.g. 6x9).
                                  Default: like the scan.
  --orientation [portrait|landscape]
                                  Page orientation.
  --columns INTEGER RANGE         Text columns per page (1-3).  [1<=x<=3]
  --align [keep|start|left|right|justify]
                                  Paragraph alignment. start = left for English, right for Hebrew.
                                  keep = as scanned.
  --align-headings                Also apply --align to headings (normally they keep theirs).
  --toc                           Add a table of contents built from the headings.
  --page-numbers                  Add page numbers in the footer.
  --title-page                    Add a title page (see --title, --subtitle, --author).
  --title TEXT                    Document title (title page and file properties).
  --subtitle TEXT                 Subtitle for the title page.
  --author TEXT                   Author for the title page and file properties.
  --keep-headers                  Keep the running headers and footers printed on the scanned pages.
  --keep-page-numbers             Keep the scan's own printed page numbers.
  --no-merge-pages                Do not join paragraphs that a page break split in two.
  --strip-nikud                   Remove Hebrew vowel points (nikud).
  --strip-teamim                  Remove cantillation marks (ta'amim).
  --no-figures                    Leave out pictures cropped from the pages.
  --regions [per-page|grouped|main-only]
                                  Pages with several texts (e.g. Gemara with Rashi): per-page = main
                                  text then each commentary, page by page; grouped = all main text,
                                  then each commentary; main-only.
  --highlight-uncertain           Highlight words the reader was unsure of (for proofreading).
  --set PATH=VALUE                Set any style option by its path, e.g. --set
                                  extras.toc_title=Inhalt. Repeatable.
  -h, --help                      Show this message and exit.
```

## prepare

```text
Usage: scantodoc prepare [OPTIONS] INPUTS...

  Get pages ready for Claude to read in a chat (no API key needed).

  Renders the pages and lists, for each one, the image to look at and the JSON file to write (see
  agent/reading-rules.md and agent/schema.json in the project). Then run `scantodoc assemble
  PROJECT`.

  INPUTS can also be one existing project folder, to hand over just some of its pages (for example
  the ones the free local reader found hard); the other pages are kept.

  Examples:
    scantodoc prepare book.pdf --pages 1-5
    scantodoc prepare ~/ScanToDoc/projects/book --pages 3,7

Options:
  --name TEXT          Name for the project (default: the first input's name).
  --projects-dir PATH  Where the project folder is kept (default: ~/ScanToDoc/projects).
  --pages TEXT         Only these pages, e.g. '1-10,15' (counting from 1).
  --dpi INTEGER        Resolution for page images.  [default: 300]
  --no-text-layer      Do not hand over text already inside the PDF.
  --json               Print the page list as JSON.
  -h, --help           Show this message and exit.
```

## assemble

```text
Usage: scantodoc assemble [OPTIONS] PROJECT

  Build the document from the page files Claude wrote after `scantodoc prepare`, then export it like
  `convert` does.

  Examples:
    scantodoc assemble ~/ScanToDoc/projects/book --check
    scantodoc assemble ~/ScanToDoc/projects/book -f docx,pdf --preset "Classic sefer"

Options:
  --check                         Only check the page files and report problems.
  --allow-missing                 Build the document even if some pages were not written.
  -f, --format TEXT               Comma-separated export formats: docx, pdf, html, md, txt, json.
                                  [default: docx]
  -o, --out PATH                  Folder for the exported files (default: next to the input).
  --preset TEXT                   A style preset name ("Keep original", "Clean modern", "Classic
                                  sefer", "Academic", or one you saved) or a preset .json file.
                                  Other style options are applied on top.
  --body-font TEXT                Font for all Latin-script text (e.g. 'Times New Roman',
                                  'Garamond').
  --hebrew-font TEXT              Font for all Hebrew/Yiddish/Aramaic text (e.g. 'Frank Ruehl CLM',
                                  'David').
  --heading-font TEXT             Latin font for all headings.
  --heading-hebrew-font TEXT      Hebrew font for all headings.
  --element-font ELEMENT=FONT     Latin font for one element: h1, h2, h3, h4, list, table, caption,
                                  footnote or quote. Repeat as needed, e.g. --element-font
                                  h1=Georgia.
  --element-hebrew-font ELEMENT=FONT
                                  Hebrew font for one element, e.g. --element-hebrew-font
                                  footnote=David.
  --rashi-font TEXT               Font for text detected in Rashi script (default: Noto Rashi
                                  Hebrew).
  --scale FLOAT                   Scale every detected size, in percent (e.g. 110).
  --size ELEMENT=PT               Exact size in points for an element (body, h1-h4, list, table,
                                  caption, footnote, quote). Repeatable or comma-separated: --size
                                  body=12,h1=24. Elements not given keep their detected size.
  --black                         Make all text black (ignore detected colours).
  --heading-color #RRGGBB         Colour for all headings.
  --color ELEMENT=#RRGGBB         Colour for one element: body, h1-h4, list, quote, caption,
                                  footnote. Repeatable.
  --link-color #RRGGBB            Colour for web links.
  --background #RRGGBB            Page background colour.
  --accent-color #RRGGBB          Colour of a line under or beside headings.
  --accent-style [underline|rule|bar]
                                  Heading accent: underline (thick line below), rule (thin line
                                  below) or bar (beside).
  --strip-bold                    Remove bold from the text (headings keep their heading look).
  --strip-italic                  Remove italic.
  --strip-underline               Remove underline.
  --bold-to-headings LEVEL        Turn short lines that are entirely bold into real headings of this
                                  level (1-4).  [1<=x<=4]
  --line-spacing FLOAT            Line spacing as a multiple (1 = single, 1.5, 2 = double).
  --space-before FLOAT            Space before each paragraph, in points.
  --space-after FLOAT             Space after each paragraph, in points.
  --first-line-indent FLOAT       First-line indent of paragraphs, in points (0 = none).
  --margins INCHES                Page margins in inches: one value for all sides, or
                                  top,right,bottom,left.
  --page-size SIZE                letter, a4, legal, a5, or WIDTHxHEIGHT in inches (e.g. 6x9).
                                  Default: like the scan.
  --orientation [portrait|landscape]
                                  Page orientation.
  --columns INTEGER RANGE         Text columns per page (1-3).  [1<=x<=3]
  --align [keep|start|left|right|justify]
                                  Paragraph alignment. start = left for English, right for Hebrew.
                                  keep = as scanned.
  --align-headings                Also apply --align to headings (normally they keep theirs).
  --toc                           Add a table of contents built from the headings.
  --page-numbers                  Add page numbers in the footer.
  --title-page                    Add a title page (see --title, --subtitle, --author).
  --title TEXT                    Document title (title page and file properties).
  --subtitle TEXT                 Subtitle for the title page.
  --author TEXT                   Author for the title page and file properties.
  --keep-headers                  Keep the running headers and footers printed on the scanned pages.
  --keep-page-numbers             Keep the scan's own printed page numbers.
  --no-merge-pages                Do not join paragraphs that a page break split in two.
  --strip-nikud                   Remove Hebrew vowel points (nikud).
  --strip-teamim                  Remove cantillation marks (ta'amim).
  --no-figures                    Leave out pictures cropped from the pages.
  --regions [per-page|grouped|main-only]
                                  Pages with several texts (e.g. Gemara with Rashi): per-page = main
                                  text then each commentary, page by page; grouped = all main text,
                                  then each commentary; main-only.
  --highlight-uncertain           Highlight words the reader was unsure of (for proofreading).
  --set PATH=VALUE                Set any style option by its path, e.g. --set
                                  extras.toc_title=Inhalt. Repeatable.
  -h, --help                      Show this message and exit.
```

## zoom

```text
Usage: scantodoc zoom [OPTIONS] IMAGE X0,Y0,X1,Y1

  Save a close-up of part of a page image, to read small print.

  BOX is on the same 0-1000 scale as page files (0,0 = top-left), e.g. 0,0,1000,500 for the top
  half.

  Example:
    scantodoc zoom pages/page-0003.jpg 0,500,500,1000

Options:
  -o, --out PATH  Where to save the close-up (default: next to the image).
  -h, --help      Show this message and exit.
```

## estimate

```text
Usage: scantodoc estimate [OPTIONS] INPUTS...

  Show what reading these files with Claude would cost (nothing is sent).

Options:
  --model TEXT  Claude model to price.  [default: claude-haiku-5-5]
  --pages TEXT  Only these pages, e.g. '1-10'.
  -h, --help    Show this message and exit.
```

## serve

```text
Usage: scantodoc serve [OPTIONS]

  Start the ScanToDoc web app (then open http://localhost:8765).

Options:
  --host TEXT     Address to listen on (127.0.0.1 = only this computer).  [default: 127.0.0.1]
  --port INTEGER  Port for the web app.  [default: 8765]
  --no-browser    Do not open the web browser automatically.
  -h, --help      Show this message and exit.
```

## preset

```text
Usage: scantodoc preset [OPTIONS] COMMAND [ARGS]...

  List, show, save and delete style presets.

Options:
  -h, --help  Show this message and exit.

Commands:
  delete  Delete a saved preset (built-in presets cannot be deleted).
  list    List the built-in and saved presets.
  save    Save the given style options as a named preset.
  show    Print a preset's full settings as JSON.
```

### preset list

```text
Usage: scantodoc preset list [OPTIONS]

  List the built-in and saved presets.

Options:
  -h, --help  Show this message and exit.
```

### preset show

```text
Usage: scantodoc preset show [OPTIONS] NAME

  Print a preset's full settings as JSON.

Options:
  -h, --help  Show this message and exit.
```

### preset save

```text
Usage: scantodoc preset save [OPTIONS] NAME

  Save the given style options as a named preset.

  Example:
    scantodoc preset save "My navy" --preset "Clean modern" --heading-color "#1F3A5F"

Options:
  --description TEXT              A short description shown in lists.
  --preset TEXT                   A style preset name ("Keep original", "Clean modern", "Classic
                                  sefer", "Academic", or one you saved) or a preset .json file.
                                  Other style options are applied on top.
  --body-font TEXT                Font for all Latin-script text (e.g. 'Times New Roman',
                                  'Garamond').
  --hebrew-font TEXT              Font for all Hebrew/Yiddish/Aramaic text (e.g. 'Frank Ruehl CLM',
                                  'David').
  --heading-font TEXT             Latin font for all headings.
  --heading-hebrew-font TEXT      Hebrew font for all headings.
  --element-font ELEMENT=FONT     Latin font for one element: h1, h2, h3, h4, list, table, caption,
                                  footnote or quote. Repeat as needed, e.g. --element-font
                                  h1=Georgia.
  --element-hebrew-font ELEMENT=FONT
                                  Hebrew font for one element, e.g. --element-hebrew-font
                                  footnote=David.
  --rashi-font TEXT               Font for text detected in Rashi script (default: Noto Rashi
                                  Hebrew).
  --scale FLOAT                   Scale every detected size, in percent (e.g. 110).
  --size ELEMENT=PT               Exact size in points for an element (body, h1-h4, list, table,
                                  caption, footnote, quote). Repeatable or comma-separated: --size
                                  body=12,h1=24. Elements not given keep their detected size.
  --black                         Make all text black (ignore detected colours).
  --heading-color #RRGGBB         Colour for all headings.
  --color ELEMENT=#RRGGBB         Colour for one element: body, h1-h4, list, quote, caption,
                                  footnote. Repeatable.
  --link-color #RRGGBB            Colour for web links.
  --background #RRGGBB            Page background colour.
  --accent-color #RRGGBB          Colour of a line under or beside headings.
  --accent-style [underline|rule|bar]
                                  Heading accent: underline (thick line below), rule (thin line
                                  below) or bar (beside).
  --strip-bold                    Remove bold from the text (headings keep their heading look).
  --strip-italic                  Remove italic.
  --strip-underline               Remove underline.
  --bold-to-headings LEVEL        Turn short lines that are entirely bold into real headings of this
                                  level (1-4).  [1<=x<=4]
  --line-spacing FLOAT            Line spacing as a multiple (1 = single, 1.5, 2 = double).
  --space-before FLOAT            Space before each paragraph, in points.
  --space-after FLOAT             Space after each paragraph, in points.
  --first-line-indent FLOAT       First-line indent of paragraphs, in points (0 = none).
  --margins INCHES                Page margins in inches: one value for all sides, or
                                  top,right,bottom,left.
  --page-size SIZE                letter, a4, legal, a5, or WIDTHxHEIGHT in inches (e.g. 6x9).
                                  Default: like the scan.
  --orientation [portrait|landscape]
                                  Page orientation.
  --columns INTEGER RANGE         Text columns per page (1-3).  [1<=x<=3]
  --align [keep|start|left|right|justify]
                                  Paragraph alignment. start = left for English, right for Hebrew.
                                  keep = as scanned.
  --align-headings                Also apply --align to headings (normally they keep theirs).
  --toc                           Add a table of contents built from the headings.
  --page-numbers                  Add page numbers in the footer.
  --title-page                    Add a title page (see --title, --subtitle, --author).
  --title TEXT                    Document title (title page and file properties).
  --subtitle TEXT                 Subtitle for the title page.
  --author TEXT                   Author for the title page and file properties.
  --keep-headers                  Keep the running headers and footers printed on the scanned pages.
  --keep-page-numbers             Keep the scan's own printed page numbers.
  --no-merge-pages                Do not join paragraphs that a page break split in two.
  --strip-nikud                   Remove Hebrew vowel points (nikud).
  --strip-teamim                  Remove cantillation marks (ta'amim).
  --no-figures                    Leave out pictures cropped from the pages.
  --regions [per-page|grouped|main-only]
                                  Pages with several texts (e.g. Gemara with Rashi): per-page = main
                                  text then each commentary, page by page; grouped = all main text,
                                  then each commentary; main-only.
  --highlight-uncertain           Highlight words the reader was unsure of (for proofreading).
  --set PATH=VALUE                Set any style option by its path, e.g. --set
                                  extras.toc_title=Inhalt. Repeatable.
  -h, --help                      Show this message and exit.
```

### preset delete

```text
Usage: scantodoc preset delete [OPTIONS] NAME

  Delete a saved preset (built-in presets cannot be deleted).

Options:
  -h, --help  Show this message and exit.
```

## fonts

```text
Usage: scantodoc fonts [OPTIONS] [COMMAND] [ARGS]...

  List the curated fonts (any other installed font name also works).

Options:
  --hebrew    Only Hebrew-script fonts.
  --latin     Only Latin-script fonts.
  -h, --help  Show this message and exit.

Commands:
  install  Install ScanToDoc's bundled free fonts (Frank Ruhl Libre, David Libre, Noto Rashi...
```

### fonts install

```text
Usage: scantodoc fonts install [OPTIONS]

  Install ScanToDoc's bundled free fonts (Frank Ruhl Libre, David Libre, Noto Rashi Hebrew, ...) for
  your user, so Word can show them too.

Options:
  -h, --help  Show this message and exit.
```

## projects

```text
Usage: scantodoc projects [OPTIONS]

  List past conversions (projects).

Options:
  --json      Print as JSON.
  -h, --help  Show this message and exit.
```

## doctor

```text
Usage: scantodoc doctor [OPTIONS]

  Check that everything ScanToDoc needs is installed, and explain what is missing.

Options:
  -h, --help  Show this message and exit.
```
