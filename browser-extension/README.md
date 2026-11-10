# ScanToDoc browser extension (free)

Convert scanned PDFs and page pictures **straight from your browser**:

- **Right-click a link** to a PDF or picture: *Convert linked PDF or picture with ScanToDoc*.
- **Right-click a picture** on a page: *Convert this picture with ScanToDoc*.
- **Viewing a PDF in Chrome or Edge?** Click the ScanToDoc button in the toolbar, then **Convert this PDF**.
- **Files on your computer:** click the ScanToDoc button, then **Convert files from this computer…**, and drop them in.

The finished Word file (or PDF, web page, Markdown or text, whichever you chose) is saved to
your **Downloads** folder, and a notice tells you when it's ready. The toolbar button shows how
far along the reading is.

This is the **free version**. Pages are read on your own computer by ScanToDoc's free reader
(Tesseract). Nothing is uploaded to the internet, and the extension never uses Claude or an
API key. The ScanToDoc app itself refuses anything else from the extension.

## What you need

1. **ScanToDoc running on your computer.** Double-click `start-windows.bat` (Windows) or
   `start-mac.command` (Mac) and leave its window open. See the main README,
   "Install and start".
2. **Tesseract**, the free reader. See "Install Tesseract" in the main README.
3. **Google Chrome or Microsoft Edge** (version 116 or newer). Other Chromium browsers such as
   Brave usually work too. Firefox and Safari are not supported yet.

## Install it

The extension isn't in the Chrome Web Store, so you add it from the folder:

**Chrome**
1. Open `chrome://extensions` (type it in the address bar).
2. Turn on **Developer mode** (top right).
3. Click **Load unpacked** and choose this `browser-extension` folder (inside the ScanToDoc folder).
4. Click the puzzle-piece icon in the toolbar and **pin** ScanToDoc, so its button is always visible.

**Edge**
1. Open `edge://extensions`.
2. Turn on **Developer mode** (on the left).
3. Click **Load unpacked** and choose this `browser-extension` folder.
4. Click the puzzle-piece icon and choose the eye icon next to ScanToDoc to show its button.

Keep the folder where it is: the browser loads the extension from it. If you move the folder,
remove the extension and load it again.

## The first time you convert something from a website

To download a PDF or picture from a web page, the extension needs your permission to read files
from websites. It asks **once**, on a page that explains why, and only when you first use it.
Files you choose from your computer never need this.

## Options

These are in the popup, and they're remembered:

- **Save as:** Word (.docx), PDF, web page, Markdown or text.
- **Look:** one of ScanToDoc's style presets (Keep original, Clean modern, Classic sefer,
  Academic, or one you saved in the app).
- **Languages:** which languages are on the pages (English, Hebrew, Yiddish, as installed for
  Tesseract).
- **Pages** (convert page only): for example `1-10, 15`.
- **Port** (⚙): only if you start ScanToDoc on a port other than 8765.

To fix text, change the style or download another format, click **Open in ScanToDoc** on a
finished conversion. It opens in the full app.

## If something goes wrong

- **"ScanToDoc isn't running on this computer"**: start it with the start file, then click
  **Try again**.
- **"…free page reader (Tesseract) isn't installed"**: install Tesseract (main README), then
  restart ScanToDoc.
- **"That link opens a web page, not a PDF or picture"**: the link leads to a page *about* the
  file. Open it, find the actual PDF, and right-click that link (or open the PDF and use the
  toolbar button).
- **"The website did not let ScanToDoc download that file"**: some sites block downloads by
  other programs. Download the file yourself, then use **Convert files from this computer…**.
- **Pictures that only exist inside the page** (`blob:` addresses) can't be fetched. Save the
  picture first, then convert it from your computer.
- **Nothing in the right-click menu inside Chrome's PDF viewer**: the viewer has its own menu.
  Use the ScanToDoc toolbar button instead.

## For developers

- Manifest V3, plain JavaScript, no build step: `background.js` (menus and messages),
  `lib/jobs.js` (fetch → upload → convert → download), `lib/api.js` (the local app's API),
  `popup.*` and `convert.*` (the two screens).
- The `key` in `manifest.json` fixes the extension's ID at `fhkcgfiapfnbhklppenjbkaabmfhpgkl`.
  The ScanToDoc app accepts requests from that ID only, and only for uploading, choosing a
  preset, and starting or stopping a **local** conversion. To allow another copy (for example
  one published to a store, which gets a new ID), start the app with
  `SCANTODOC_EXTENSION_IDS=<id>`.
- Tests: `pytest tests/test_extension.py` loads the extension into Chromium and converts real
  files.
