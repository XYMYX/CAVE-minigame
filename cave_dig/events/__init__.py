"""Alle Ereignisse an einem Ort.

EVENT_TYPES ist die Liste, die das Spiel kennt. Ein neues Ereignis wird
hier sichtbar, nicht irgendwo versteckt per Zauber-Import.
"""

from __future__ import annotations

from cave_dig.config import GameConfig
from cave_dig.events.base import CaveEvent
from cave_dig.events.cave_in import CaveInEvent
from cave_dig.events.darkness import DarknessEvent
from cave_dig.events.explosion import ExplosionEvent
from cave_dig.events.ore_vein import OreVeinEvent

EVENT_TYPES: dict[str, type[CaveEvent]] = {
    "cave_in": CaveInEvent,
    "darkness": DarknessEvent,
    "explosion": ExplosionEvent,
    "ore_vein": OreVeinEvent,
}


def create_event(event_id: str, config: GameConfig) -> CaveEvent | None:
    cls = EVENT_TYPES.get(event_id)
    if cls is None:
        return None
    duration = config.event_durations.get(event_id, 5.0)
    return cls(duration)
