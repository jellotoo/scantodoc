#!/bin/bash
# ScanToDoc for Mac (and Linux): double-click this file to start the app.
# The first start installs everything it needs (a few minutes); later starts are quick.
cd "$(dirname "$0")" || exit 1
HOMEDIR="${SCANTODOC_HOME:-$HOME/ScanToDoc}"
VENV="$HOMEDIR/venv"
PY="$VENV/bin/python"

pause_and_exit() {
  echo
  read -r -p "Press Return to close this window. " _
  exit "$1"
}

if ! { [ -x "$PY" ] && "$PY" -m scantodoc --version >/dev/null 2>&1; }; then
  echo
  echo "  Setting up ScanToDoc for the first time. This takes a few minutes..."
  echo
  BASEPY=""
  for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1 &&
      "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
      BASEPY="$candidate"
      break
    fi
  done
  if [ -z "$BASEPY" ]; then
    echo "  Python 3.10 or newer is not installed. Your browser will now open the Python download page."
    echo "  Install it, then double-click start-mac.command again."
    open "https://www.python.org/downloads/macos/" 2>/dev/null || xdg-open "https://www.python.org/downloads/" 2>/dev/null
    pause_and_exit 1
  fi
  mkdir -p "$HOMEDIR"
  "$BASEPY" -m venv "$VENV" || { echo "  Could not create the Python environment."; pause_and_exit 1; }
  "$PY" -m pip install --quiet --disable-pip-version-check --upgrade pip
  if ! "$PY" -m pip install --quiet --disable-pip-version-check -e "$PWD"; then
    echo "  Setup did not finish. Check the internet connection and try again."
    pause_and_exit 1
  fi
  # PDF export needs Chrome, Edge or Chromium; fetch a private Chromium only if none is found.
  if ! "$PY" -c 'import sys; from scantodoc import browser; sys.exit(0 if browser.available() else 1)' >/dev/null 2>&1; then
    "$PY" -m playwright install chromium
  fi
  if ! command -v tesseract >/dev/null 2>&1 && command -v brew >/dev/null 2>&1; then
    echo
    read -r -p "  Install Tesseract, the free page reader, with Homebrew now? [Y/n] " answer
    case "$answer" in
      [nN]*) ;;
      *) brew install tesseract tesseract-lang ;;
    esac
  fi
  echo
  read -r -p "  Install ScanToDoc's free Hebrew and English fonts, so Word can show them? [Y/n] " answer
  case "$answer" in
    [nN]*) ;;
    *) "$PY" -m scantodoc fonts install ;;
  esac
  echo
  "$PY" -m scantodoc doctor
  echo
fi

echo "  Starting ScanToDoc at http://localhost:8765  (close this window to stop it)"
"$PY" -m scantodoc serve || pause_and_exit 1
