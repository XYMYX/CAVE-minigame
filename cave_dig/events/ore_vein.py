"""Unter der Spitzhacke erscheint eine Ader Kristall."""

from __future__ import annotations

from cave_dig.events.base import CaveEvent


class OreVeinEvent(CaveEvent):
    id = "ore_vein"

    def on_start(self, game: object) -> None:
        rng = game.rng  # type: ignore[attr-defined]
        size = game.block_size  # type: ignore[attr-defined]
        col = int(game.pickaxe.x // size)  # type: ignore[attr-defined]
        row = int(game.pickaxe.y // size)  # type: ignore[attr-defined]
        for dc in range(-1, 3):
            for dr in range(1, 5):
                if rng.random() > 0.82:
                    continue
                # Urgestein bleibt, sonst reißt die Ader Barrieren auf.
                if game.world.type_of(col + dc, row + dr) == "bedrock":  # type: ignore[attr-defined]
                    continue
                game.world.set_kind(col + dc, row + dr, "gem")  # type: ignore[attr-defined]

    def on_update(self, game: object, dt: float) -> None:
        super().on_update(game, dt)
