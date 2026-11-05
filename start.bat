@echo off
REM Cave Dig starten. Legt beim ersten Mal eine virtuelle Umgebung an.
setlocal
cd /d "%~dp0"

REM Ganz neue Python-Versionen haben oft noch kein fertiges pygame. Darum zuerst diese.
set "PY="
for %%V in (3.12 3.13 3.11 3.10) do (
  if not defined PY py -%%V -c "pass" >nul 2>&1 && set "PY=py -%%V"
)
if not defined PY (
  where py >nul 2>&1 && (set "PY=py -3") || (set "PY=python")
)

%PY% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
  echo Python 3.10 oder neuer fehlt. Bitte von https://www.python.org/downloads/ installieren.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  %PY% -m venv .venv
  if errorlevel 1 goto :fehler
)

REM Die Merkdatei ist eine Kopie von requirements.txt nach erfolgreicher Installation.
REM So holt der naechste Start eine abgebrochene Installation nach,
REM und neue Pakete kommen von selbst dazu.
fc /b requirements.txt ".venv\installiert.txt" >nul 2>&1
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :fehler
  copy /y requirements.txt ".venv\installiert.txt" >nul
)

REM Ein Absturz soll den Dauerstream nicht beenden: nach 10 Sekunden neu starten.
REM Code 0 ist ein normales Ende. Code 3 ist eine falsche Konfiguration, da hilft kein Neustart.
:spielen
".venv\Scripts\python.exe" -m cave_dig %*
set "CODE=%errorlevel%"
if "%CODE%"=="0" exit /b 0
if "%CODE%"=="3" goto :fehler
echo.
echo Spiel beendet mit Code %CODE%. Neustart in 10 Sekunden. Abbrechen: dieses Fenster schliessen.
ping -n 11 127.0.0.1 >nul
goto :spielen

:fehler
echo.
echo Start fehlgeschlagen. Steht die Meldung oben, und in logs\cave_dig.log?
pause
exit /b 1
