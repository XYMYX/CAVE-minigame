"""Namen der Zeichenmuster für Blöcke.

Die Muster selbst malt textures.py. Hier steht nur die Liste der erlaubten
Namen, damit die Konfiguration geprüft werden kann, ohne Pygame zu starten.
"""

from __future__ import annotations

# "none" ist Luft: die wird nicht gezeichnet.
PATTERNS = frozenset(
    {
        "none",
        "speckles",
        "pebbles",
        "cracks",
        "ore",
        "crystals",
        "veins",
        "charge",
    }
)
