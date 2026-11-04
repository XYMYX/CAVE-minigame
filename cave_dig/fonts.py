"""Mehrere Schriften hintereinander, damit Chat-Namen lesbar bleiben.

Pygame nimmt pro Text eine Schrift. Ein Name kann aber lateinische Buchstaben
und zum Beispiel Hangul mischen. FontChain prüft Zeichen für Zeichen, welche
Datei das Zeichen wirklich enthält, und setzt die Stücke aneinander.

Fehlt ein Zeichen überall (oft Emoji), lassen wir es weg statt eine leere
Box zu malen.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pygame

log = logging.getLogger("cave_dig.fonts")

# Reihenfolge: erst die Schrift für normalen Text, dann Sonderzeichen.
_FONT_FILES = (
    "NotoSans-Regular.ttf",
    "NotoSansArabic-Regular.ttf",
    "NotoSansDevanagari-Regular.ttf",
    "NotoSansThai-Regular.ttf",
    "DejaVuSans.ttf",
    "wqy-microhei.ttc",
)


class FontChain:
    def __init__(self, fonts: list[pygame.font.Font]) -> None:
        self.fonts = fonts
        self._notdef = [font.metrics("\ue000") for font in fonts]
        self._pick: dict[str, int] = {}

    def render(self, text: str, color: tuple[int, int, int]) -> pygame.Surface:
        if not text:
            return pygame.Surface((1, 1), pygame.SRCALPHA)
        runs: list[tuple[pygame.font.Font, str]] = []
        current_index = -1
        current: list[str] = []
        for ch in text:
            index = self._index_for(ch)
            if index < 0:
                continue
            if index != current_index and current:
                runs.append((self.fonts[current_index], "".join(current)))
                current = [ch]
            else:
                current.append(ch)
            current_index = index
        if current and current_index >= 0:
            runs.append((self.fonts[current_index], "".join(current)))
        if not runs:
            return pygame.Surface((1, 1), pygame.SRCALPHA)
        parts = []
        for font, piece in runs:
            try:
                parts.append(font.render(piece, True, color))
            except (pygame.error, ValueError):
                # Unsichtbare Zeichen wie U+FE0F allein haben keine Breite.
                # pygame wirft dann einen Fehler. Das Stück zeigt ohnehin nichts.
                continue
        if not parts:
            return pygame.Surface((1, 1), pygame.SRCALPHA)
        width = sum(part.get_width() for part in parts)
        height = max(part.get_height() for part in parts)
        image = pygame.Surface((max(1, width), max(1, height)), pygame.SRCALPHA)
        x = 0
        for part in parts:
            image.blit(part, (x, height - part.get_height()))
            x += part.get_width()
        return image

    def _index_for(self, ch: str) -> int:
        cached = self._pick.get(ch)
        if cached is not None:
            return cached
        chosen = -1
        for index, font in enumerate(self.fonts):
            metrics = font.metrics(ch)
            if not metrics or metrics[0] is None:
                continue
            if metrics == self._notdef[index]:
                continue
            chosen = index
            break
        self._pick[ch] = chosen
        return chosen


class FontBook:
    """Hält Schriftgrößen und schon gezeichnete Texte vor."""

    def __init__(self, font_dir: Path) -> None:
        self.font_dir = font_dir
        self._chains: dict[int, FontChain] = {}
        self._cache: dict[tuple[str, int, tuple[int, int, int]], pygame.Surface] = {}
        self._fallback_warned = False

    def render(self, text: str, size: int, color: tuple[int, int, int]) -> pygame.Surface:
        key = (text, size, color)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        image = self._chain(size).render(text, color)
        self._cache[key] = image
        if len(self._cache) > 500:
            # Alte Zeilen wegwerfen. Namen wechseln, der Speicher soll nicht wachsen.
            for old in list(self._cache)[:250]:
                self._cache.pop(old, None)
        return image

    def render_shadow(
        self,
        text: str,
        size: int,
        color: tuple[int, int, int],
    ) -> pygame.Surface:
        front = self.render(text, size, color)
        shadow = self.render(text, size, (12, 8, 10))
        image = pygame.Surface((front.get_width() + 1, front.get_height() + 1), pygame.SRCALPHA)
        image.blit(shadow, (1, 1))
        image.blit(front, (0, 0))
        return image

    def _chain(self, size: int) -> FontChain:
        existing = self._chains.get(size)
        if existing is not None:
            return existing
        fonts: list[pygame.font.Font] = []
        for file_name in _FONT_FILES:
            path = self.font_dir / file_name
            try:
                fonts.append(pygame.font.Font(str(path), size))
            except (pygame.error, FileNotFoundError) as exc:
                if not self._fallback_warned:
                    log.warning("Schrift %s nicht geladen (%s). Nutze die Ersatzschrift.", path.name, exc)
                    self._fallback_warned = True
        if not fonts:
            fonts.append(pygame.font.Font(None, size))
        chain = FontChain(fonts)
        self._chains[size] = chain
        return chain
