"""Die Höhle als Gitter.

Jede Zelle ist ein Block. Die Höhle hat kein Ende: Reihen entstehen, wenn
die Spitzhacke sich nähert, und Reihen weit oben werden vergessen. Dieselbe
Seed-Zahl baut dieselbe Reihe immer gleich wieder auf. Zerbrochene Blöcke
merken wir uns nur, solange die Reihe noch im Speicher ist. Darum werfen
wir nur Reihen weg, die weit über der Spitzhacke liegen.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from cave_dig.config import Band, BlockType, GameConfig


@dataclass
class Block:
    type_id: str
    hp: int
    max_hp: int


@dataclass(frozen=True)
class HitResult:
    """Was ein Treffer bewirkt hat. broken heißt: die Zelle ist jetzt Luft."""

    broken: bool
    unbreakable: bool
    type_id: str
    points: int
    explosive: bool
    col: int
    row: int


@dataclass(frozen=True)
class Destroyed:
    type_id: str
    points: int
    explosive: bool
    color: tuple[int, int, int]


class World:
    def __init__(self, config: GameConfig, seed: int) -> None:
        self.config = config
        self.seed = seed & 0x7FFFFFFF
        self.cols = config.columns
        self.block_size = config.block_size
        self.wall = config.wall_columns
        self.types = config.blocks
        self.bands = config.bands
        self.cells: dict[tuple[int, int], Block] = {}
        self.generated_rows: set[int] = set()
        self.last_hit: dict[tuple[int, int], float] = {}
        # Reihen darüber sind vergessen und werden nicht wieder aufgebaut.
        self.first_kept_row = 0

    def ensure_through(self, row: int) -> None:
        for current in range(self.first_kept_row, max(0, row) + 1):
            if current not in self.generated_rows:
                self._generate_row(current)

    def discard_above(self, row: int) -> None:
        """Gibt Reihen frei, die niemand mehr sieht. Speicher bleibt flach."""
        self.first_kept_row = max(self.first_kept_row, row)
        stale = [existing for existing in self.generated_rows if existing < row]
        for existing in stale:
            for col in range(self.cols):
                self.cells.pop((col, existing), None)
            self.generated_rows.discard(existing)
        self.last_hit = {key: when for key, when in self.last_hit.items() if key[1] >= row}

    def in_columns(self, col: int) -> bool:
        return 0 <= col < self.cols

    def is_wall(self, col: int) -> bool:
        return col < self.wall or col >= self.cols - self.wall

    def block_at(self, col: int, row: int) -> Block | None:
        if not self.in_columns(col) or row < 0:
            return None
        if row not in self.generated_rows:
            self._generate_row(row)
        return self.cells.get((col, row))

    def is_solid(self, col: int, row: int) -> bool:
        # Neben dem Gitter ist massiv, damit die Spitzhacke nicht hinausfällt.
        if not self.in_columns(col):
            return row >= 0
        if row < 0:
            return False
        block = self.block_at(col, row)
        if block is None:
            return False
        return self.types[block.type_id].solid

    def is_air(self, col: int, row: int) -> bool:
        if row < 0 and self.in_columns(col):
            return True
        return self.in_columns(col) and row >= 0 and not self.is_solid(col, row)

    def type_of(self, col: int, row: int) -> str:
        block = self.block_at(col, row)
        if block is None:
            return "air" if row < 0 else "bedrock"
        return block.type_id

    def set_kind(self, col: int, row: int, type_id: str) -> None:
        if not self.in_columns(col) or row < 0 or type_id not in self.types:
            return
        if row not in self.generated_rows:
            self._generate_row(row)
        # Wände bleiben Urgestein, sonst gräbt ein Ereignis den Rand weg.
        if self.is_wall(col) and type_id != "bedrock":
            return
        self.cells[(col, row)] = self._make(type_id)

    def touch(self, col: int, row: int, now: float, cooldown: float) -> HitResult | None:
        """Ein Hieb. None heißt: zu früh wieder auf derselben Zelle."""
        if not self.is_solid(col, row):
            return None
        key = (col, row)
        last = self.last_hit.get(key, -1_000_000.0)
        if now - last < cooldown:
            return None
        self.last_hit[key] = now
        block = self.block_at(col, row)
        if block is None:
            return None
        spec = self.types[block.type_id]
        if spec.unbreakable:
            return HitResult(False, True, block.type_id, 0, False, col, row)
        block.hp -= 1
        if block.hp > 0:
            return HitResult(False, False, block.type_id, 0, False, col, row)
        points = spec.points
        explosive = spec.explosive
        type_id = block.type_id
        self.cells[key] = self._make("air")
        return HitResult(True, False, type_id, points, explosive, col, row)

    def destroy(self, col: int, row: int) -> Destroyed | None:
        """Räumt eine Zelle sofort. Urgestein und Luft bleiben, wie sie sind."""
        if not self.is_solid(col, row):
            return None
        block = self.block_at(col, row)
        if block is None:
            return None
        spec = self.types[block.type_id]
        if spec.unbreakable:
            return None
        self.cells[(col, row)] = self._make("air")
        return Destroyed(block.type_id, spec.points, spec.explosive, spec.color)

    def rect(self, col: int, row: int) -> tuple[float, float, float, float]:
        size = self.block_size
        return float(col * size), float(row * size), float(size), float(size)

    def _make(self, type_id: str) -> Block:
        spec = self.types[type_id]
        hp = spec.hits
        return Block(type_id, hp, spec.hits)

    def _generate_row(self, row: int) -> None:
        if row in self.generated_rows or row < 0:
            return
        for col in range(self.cols):
            self.cells[(col, row)] = self._make(self._kind(col, row))
        self.generated_rows.add(row)

    def _kind(self, col: int, row: int) -> str:
        if self.is_wall(col) or row < 0:
            return "bedrock"
        if row < self.config.sky_rows:
            return "air"
        if self._is_shelf(row) and col not in self._gap_columns(row):
            return "bedrock"
        band = self._band(row)
        origin_col = self.wall + ((col - self.wall) // 3) * 3
        origin_row = row - (row % 2)
        origin = random.Random(self._mix(origin_col, origin_row, 0xA5A5))
        if band.veins and origin.random() < band.vein_chance:
            ore = _weighted(origin, band.veins)
            cell = random.Random(self._mix(col, row, 17))
            if cell.random() < 0.78:
                return ore
        cell = random.Random(self._mix(col, row, 91))
        return _weighted(cell, band.fill)

    def _is_shelf(self, row: int) -> bool:
        every = self.config.shelf_every
        if row < every * 2:
            return False
        return row % every == 0

    def _gap_columns(self, row: int) -> set[int]:
        playable = self.cols - 2 * self.wall
        gap = min(self.config.shelf_gap, playable)
        span = playable - gap
        # Nicht direkt % nehmen: Die letzten Bits von _mix ändern sich bei
        # jeder 16. Reihe nicht, und alle Lücken lägen übereinander.
        start = self.wall + random.Random(self._mix(0, row, 3)).randrange(span + 1)
        return set(range(start, start + gap))

    def _band(self, row: int) -> Band:
        for band in self.bands:
            if row < band.until_row:
                return band
        return self.bands[-1]

    def _mix(self, col: int, row: int, salt: int) -> int:
        # Feste Mischung statt random.Random-Reihenfolge. Dieselbe Zelle
        # liefert immer dieselbe Zahl, egal wann wir sie erzeugen.
        value = (self.seed + 1) * 1_000_003
        value ^= col * 734_287
        value ^= row * 912_931
        value ^= salt * 1_299_721
        return value & 0x7FFFFFFF


def _weighted(rng: random.Random, weights: dict[str, int]) -> str:
    total = sum(weights.values())
    roll = rng.randrange(total)
    running = 0
    for name, weight in weights.items():
        running += weight
        if roll < running:
            return name
    return next(iter(weights))
