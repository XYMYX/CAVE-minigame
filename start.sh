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
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
fi

exec .venv/bin/python -m cave_dig "$@"
