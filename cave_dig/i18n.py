"""Texte fürs Bild, aus locales/en.yaml und locales/de.yaml.

Die Schlüssel bleiben in beiden Dateien gleich. Nur die Werte ändern sich.
Fehlt eine Sprache oder ein einzelner Schlüssel, nimmt das Spiel Englisch.
So stirbt ein Dauerstream nicht, weil eine neue Zeile nur in einer Datei steht.

Log und Kommentare im Code bleiben, wie sie sind. Hier geht es nur um
Buchstaben, die ein Zuschauer im Fenster sieht.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from cave_dig.paths import project_path

log = logging.getLogger("cave_dig.i18n")

# Jede Zeichenkette im Fenster hat einen Schlüssel. Kommt eine neue dazu,
# hier eintragen und denselben Schlüssel in locales/en.yaml und locales/de.yaml.
REQUIRED_KEYS = (
    "hud.round",
    "hud.depth",
    "hud.score",
    "hud.meters",
    "hud.record",
    "hud.pickaxe",
    "hud.votes_left",
    "hud.votes_right",
    "hud.hint",
    "hud.hint_fallback",
    "hud.miners",
    "hud.points_votes",
    "hud.empty",
    "hud.unknown",
    "round.over",
    "round.broken",
    "round.stuck",
    "round.score",
    "round.depth",
    "round.next",
    "events.cave_in",
    "events.darkness",
    "events.explosion",
    "events.ore_vein",
    "status.simulator",
    "status.twitch",
    "status.quota",
    "status.rate",
    "status.ended",
    "status.not_found",
    "status.auth",
    "status.forbidden",
    "status.other",
    "status.missing",
    "status.oauth_missing",
    "status.ready",
    "status.connecting",
)


class LocaleError(Exception):
    """Eine Sprachdatei hat nicht die erwartete Form."""


class Catalog:
    """Nachschlagewerk für eine Sprache, mit Englisch als Reserve."""

    def __init__(self, language: str, active: dict[str, str], fallback: dict[str, str]) -> None:
        self.language = language
        self.active = active
        self.fallback = fallback

    def t(self, key: str, **kwargs: object) -> str:
        """Holt eine Zeile und setzt Platzhalter wie {n} ein."""
        template = self.active.get(key)
        if template is None:
            template = self.fallback.get(key, key)
        if not kwargs:
            return template
        try:
            return template.format(**kwargs)
        except (IndexError, KeyError, ValueError):
            log.warning("Platzhalter in '%s' passen nicht: %s", key, template)
            return template


def flatten_strings(node: object, prefix: str = "") -> dict[str, str]:
    """Macht aus verschachteltem YAML flache Schlüssel wie hud.depth."""
    if not isinstance(node, dict):
        raise LocaleError(f"Sprachdatei muss aus Gruppen bestehen, nicht aus {type(node).__name__}.")
    flat: dict[str, str] = {}
    for raw_key, value in node.items():
        name = f"{prefix}.{raw_key}" if prefix else str(raw_key)
        if isinstance(value, dict):
            flat.update(flatten_strings(value, name))
        elif isinstance(value, str):
            flat[name] = value
        else:
            raise LocaleError(f"'{name}' muss Text sein.")
    return flat


def load_catalog(language: str, directory: Path | None = None) -> Catalog:
    """Lädt die gewählte Sprache. Unbekanntes oder kaputtes YAML wird Englisch."""
    folder = directory or project_path("locales")
    english = _read_locale(folder / "en.yaml") or {}
    code = _clean_code(language)
    if code == "en":
        return Catalog("en", english, english)
    chosen = _read_locale(folder / f"{code}.yaml")
    if chosen is None:
        log.warning("Sprache '%s' fehlt oder ist ungültig. Anzeige bleibt Englisch.", code)
        return Catalog("en", english, english)
    return Catalog(code, chosen, english)


def _clean_code(language: str) -> str:
    text = (language or "en").strip().lower()
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-_")
    if not text or len(text) > 16 or any(char not in allowed for char in text):
        return "en"
    return text


def _read_locale(path: Path) -> dict[str, str] | None:
    if not path.is_file():
        return None
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        log.warning("Sprachdatei %s nicht lesbar: %s", path.name, exc)
        return None
    if loaded is None:
        return {}
    try:
        return flatten_strings(loaded)
    except LocaleError as exc:
        log.warning("Sprachdatei %s: %s", path.name, exc)
        return None
