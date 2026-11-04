"""Die Lampe wird für ein paar Sekunden klein."""

from __future__ import annotations

from cave_dig.events.base import CaveEvent


class DarknessEvent(CaveEvent):
    id = "darkness"

    def light_scale(self) -> float:
        # Kurz eintauchen, dunkel bleiben, wieder auftauchen.
        if self.elapsed < 0.45:
            k = self.elapsed / 0.45
        elif self.duration - self.elapsed < 0.7:
            k = max(0.0, (self.duration - self.elapsed) / 0.7)
        else:
            k = 1.0
        return 1.0 - 0.78 * k

    def on_update(self, game: object, dt: float) -> None:
        super().on_update(game, dt)
