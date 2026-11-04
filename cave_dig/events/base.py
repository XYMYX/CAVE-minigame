"""Grundgerüst für ein Ereignis.

Ein Ereignis hat drei Aufgaben:
  on_start   einmal, wenn es beginnt (Blöcke ändern, Schaden, ...)
  on_update  jeden Frame, solange es läuft
  light_scale  wie hell die Höhle gerade ist (1 = normal, kleiner = dunkler)

Die Banner-Zeit steckt in duration. Unterklassen rufen super().on_update
auf, damit elapsed und done von allein stimmen.

So fügst du ein eigenes Ereignis hinzu: Datei hier anlegen, Klasse von
CaveEvent ableiten, in events/__init__.py in EVENT_TYPES eintragen,
in config.yaml unter events.ids und events.aliases ergänzen, und den
Banner-Text in locales/en.yaml und locales/de.yaml unter events. setzen.
"""

from __future__ import annotations


class CaveEvent:
    id = "base"
    # Der Text im Banner steht in locales/*.yaml unter events.<id>.

    def __init__(self, duration: float) -> None:
        self.duration = duration
        self.elapsed = 0.0
        self.done = False

    def on_start(self, game: object) -> None:
        return None

    def on_update(self, game: object, dt: float) -> None:
        self.elapsed += dt
        if self.elapsed >= self.duration:
            self.done = True

    def light_scale(self) -> float:
        return 1.0
