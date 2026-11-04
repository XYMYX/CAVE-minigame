"""Pfade relativ zum Projektordner, nicht zum aktuellen Arbeitsverzeichnis.

start.bat wechselt zwar in den Projektordner, aber ein Test oder ein
Doppelklick kann das Spiel auch von woanders aus aufrufen. Darum rechnen
wir Pfade von dieser Datei aus: cave_dig/paths.py liegt eine Ebene unter
dem Ordner, in dem config.yaml steht.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def project_path(*parts: str) -> Path:
    """Baut einen Pfad ab dem Projektordner. Beispiel: project_path('data', 'stand.json')."""
    return PROJECT_ROOT.joinpath(*parts)
