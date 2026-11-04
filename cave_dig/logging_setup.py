"""Schreibt ein Log auf die Platte und zusätzlich in die Konsole.

Ein Dauerstream läuft, während du schläfst. Wenn der Chat ausfällt, steht
der Grund in logs/cave_dig.log und nicht nur in einem Fenster, das schon
zu ist. Die Datei wird bei 2 MB abgeschnitten und es bleiben ein paar
ältere Stücke (cave_dig.log.1, ...).
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_dir: Path) -> None:
    root = logging.getLogger()
    if getattr(root, "_cave_dig_ready", False):
        return
    root.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / "cave_dig.log",
            maxBytes=2_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError as exc:
        root.warning("Logdatei nicht angelegt (%s). Es bleibt bei der Konsole.", exc)

    # Marker, damit Tests oder ein zweiter Aufruf keine doppelten Zeilen erzeugen.
    root._cave_dig_ready = True  # type: ignore[attr-defined]
