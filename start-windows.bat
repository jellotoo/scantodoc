@echo off
rem ScanToDoc for Windows: double-click this file to start the app.
rem The first start installs everything it needs (a few minutes); later starts are quick.
setlocal
cd /d "%~dp0"
title ScanToDoc
set "HOMEDIR=%USERPROFILE%\ScanToDoc"
if defined SCANTODOC_HOME set "HOMEDIR=%SCANTODOC_HOME%"
set "VENV=%HOMEDIR%\venv"
set "PY=%VENV%\Scripts\python.exe"

if exist "%PY%" (
  "%PY%" -m scantodoc --version >nul 2>&1 && goto run
)

echo.
echo  Setting up ScanToDoc for the first time. This takes a few minutes...
echo.
set "BASEPY="
where py >nul 2>&1 && py -3 --version >nul 2>&1 && set "BASEPY=py -3"
if not defined BASEPY (
  where python >nul 2>&1 && python --version >nul 2>&1 && set "BASEPY=python"
)
if not defined BASEPY (
  echo  Python is not installed. Your browser will now open the Python download page.
  echo  Install Python 3.10 or newer, and tick "Add python.exe to PATH" in the installer.
  echo  Then double-click start-windows.bat again.
  start "" "https://www.python.org/downloads/windows/"
  pause
  exit /b 1
)
if not exist "%HOMEDIR%" mkdir "%HOMEDIR%"
%BASEPY% -m venv "%VENV%"
if errorlevel 1 goto failed
"%PY%" -m pip install --quiet --disable-pip-version-check --upgrade pip
"%PY%" -m pip install --quiet --disable-pip-version-check -e "%~dp0."
if errorlevel 1 goto failed

rem PDF export uses Microsoft Edge, which every Windows has; fetch a private copy of Chromium only if needed.
"%PY%" -c "import sys; from scantodoc import browser; sys.exit(0 if browser.available() else 1)" >nul 2>&1
if errorlevel 1 "%PY%" -m playwright install chromium

echo.
choice /C YN /M "  Install ScanToDoc's free Hebrew and English fonts, so Word can show them"
if not errorlevel 2 "%PY%" -m scantodoc fonts install

echo.
"%PY%" -m scantodoc doctor
echo.
echo  Tesseract (the free reader) is optional. Without it, use Claude in the app.
echo  See README.md, "Install Tesseract", to add it.
echo.

:run
echo  Starting ScanToDoc at http://localhost:8765  (close this window to stop it)
"%PY%" -m scantodoc serve
if errorlevel 1 pause
exit /b 0

:failed
echo.
echo  Setup did not finish. Check the internet connection and try again.
echo  If it keeps failing, see README.md, "If something goes wrong".
pause
exit /b 1
