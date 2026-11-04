#!/usr/bin/env bash
# Cave Dig starten. Legt beim ersten Mal eine virtuelle Umgebung an.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 fehlt. Bitte von https://www.python.org/downloads/ installieren (3.10 oder neuer)."
  exit 1
fi

if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "Python ist zu alt. Bitte Version 3.10 oder neuer."
  exit 1
fi

if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi

# Die Merkdatei entsteht erst nach einer erfolgreichen Installation.
# So holt der nächste Start eine abgebrochene Installation nach.
if [[ ! -f .venv/installiert.txt ]]; then
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
  touch .venv/installiert.txt
fi

# Ein Absturz soll den Dauerstream nicht beenden: nach 10 Sekunden neu starten.
# Code 0 ist ein normales Ende. Code 3 ist eine falsche Konfiguration.
while true; do
  code=0
  .venv/bin/python -m cave_dig "$@" || code=$?
  if [[ $code -eq 0 || $code -eq 3 ]]; then
    exit "$code"
  fi
  echo "Spiel beendet mit Code $code. Neustart in 10 Sekunden. Abbrechen: Strg+C."
  sleep 10
done
