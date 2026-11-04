"""Eine Ladung geht neben der Spitzhacke hoch, nicht genau auf ihr."""

from __future__ import annotations

from cave_dig.events.base import CaveEvent


class ExplosionEvent(CaveEvent):
    id = "explosion"

    def on_start(self, game: object) -> None:
        rng = game.rng  # type: ignore[attr-defined]
        size = game.block_size  # type: ignore[attr-defined]
        col = int(game.pickaxe.x // size)  # type: ignore[attr-defined]
        row = int(game.pickaxe.y // size)  # type: ignore[attr-defined]
        # Versetzt, damit das Ereignis ein Loch macht und nicht immer tötet.
        game.queue_explosion(  # type: ignore[attr-defined]
            col + rng.choice((-2, -1, 1, 2)),
            row + rng.choice((2, 3, 4)),
        )

    def on_update(self, game: object, dt: float) -> None:
        super().on_update(game, dt)
