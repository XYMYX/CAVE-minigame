"""Decke bricht ein: über der Spitzhacke entstehen Brocken."""

from __future__ import annotations

from cave_dig.events.base import CaveEvent


class CaveInEvent(CaveEvent):
    id = "cave_in"

    def on_start(self, game: object) -> None:
        # game ist das Game-Objekt. Wir tippen hier nicht streng, damit dieses
        # Modul die große Spielklasse nicht importieren muss (Kreis-Import).
        rng = game.rng  # type: ignore[attr-defined]
        size = game.block_size  # type: ignore[attr-defined]
        col = int(game.pickaxe.x // size)  # type: ignore[attr-defined]
        row = int(game.pickaxe.y // size)  # type: ignore[attr-defined]
        placed = 0
        for _ in range(48):
            c = col + rng.randint(-2, 2)
            r = row + rng.randint(-4, 0)
            if game.world.is_air(c, r) and not game.world.is_wall(c):  # type: ignore[attr-defined]
                kind = "gravel" if rng.random() < 0.55 else "stone"
                game.world.set_kind(c, r, kind)  # type: ignore[attr-defined]
                placed += 1
            if placed >= 8:
                break
        game.pickaxe.integrity -= game.config.cave_in_damage  # type: ignore[attr-defined]
        game.shake = max(game.shake, 8)  # type: ignore[attr-defined]
        game.spawn_burst(game.pickaxe.x, game.pickaxe.y, (140, 120, 100), 16)  # type: ignore[attr-defined]

    def on_update(self, game: object, dt: float) -> None:
        super().on_update(game, dt)
