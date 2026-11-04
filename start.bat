@echo off
REM Cave Dig starten. Legt beim ersten Mal eine virtuelle Umgebung an.
setlocal
cd /d "%~dp0"

where py >nul 2>&1 && (set "PY=py -3") || (set "PY=python")

%PY% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
  echo Python 3.10 oder neuer fehlt. Bitte von https://www.python.org/downloads/ installieren.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  %PY% -m venv .venv
  if errorlevel 1 goto :fehler
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :fehler
)

".venv\Scripts\python.exe" -m cave_dig %*
if errorlevel 1 goto :fehler
exit /b 0

:fehler
echo.
echo Start fehlgeschlagen. Steht die Meldung oben, und in logs\cave_dig.log?
pause
exit /b 1
