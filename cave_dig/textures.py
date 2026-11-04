"""Eigene Pixel-Blöcke, 16 mal 16.

Es werden keine fremden Spielgrafiken geladen. Jedes Muster ist hier
gezeichnet. Liegt in assets/textures schon eine PNG mit dem Namen des
Blocks, gewinnt diese Datei. So kannst du in einem Malprogramm nachziehen
und das Spiel benutzt deine Fassung. Fehlt die PNG, wird sie beim Start
erzeugt und gespeichert.

Muster-Namen stehen in blockdefs.py. Ein neues Muster: Funktion schreiben
und in _BUILDERS eintragen.
"""

from __future__ import annotations

import random
from pathlib import Path

import pygame

from cave_dig.config import BlockType

def nearest_scale(source: pygame.Surface, size: tuple[int, int]) -> pygame.Surface:
    """Vergrößert Pixel als Kästchen, ohne sie zu verwischen.

    pygame.transform.scale ist je nach Version weich. Für diese Blöcke
    soll ein Quellpixel ein klares Kästchen bleiben.
    """
    sw, sh = source.get_size()
    dw, dh = size
    scaled = pygame.Surface(size, pygame.SRCALPHA)
    for y in range(dh):
        sy = min(sh - 1, y * sh // dh)
        for x in range(dw):
            sx = min(sw - 1, x * sw // dw)
            scaled.set_at((x, y), source.get_at((sx, sy)))
    return scaled


def _clamp_color(color: tuple[int, int, int]) -> tuple[int, int, int]:
    return tuple(max(0, min(255, int(channel))) for channel in color)  # type: ignore[return-value]


def _shift(color: tuple[int, int, int], delta: int) -> tuple[int, int, int]:
    return _clamp_color((color[0] + delta, color[1] + delta, color[2] + delta))


def _surface() -> pygame.Surface:
    return pygame.Surface((16, 16), pygame.SRCALPHA)


def _fill_noise(
    surf: pygame.Surface,
    rng: random.Random,
    color: tuple[int, int, int],
    spread: int,
) -> None:
    for y in range(16):
        for x in range(16):
            delta = rng.randint(-spread, spread)
            surf.set_at((x, y), _shift(color, delta))


def _bevel(surf: pygame.Surface) -> None:
    """Helle Kante oben/links, dunkle Kante unten/rechts. Das Gitter wird lesbar."""
    for i in range(16):
        surf.set_at((i, 0), _shift(surf.get_at((i, 0))[:3], 28))
        surf.set_at((0, i), _shift(surf.get_at((0, i))[:3], 16))
        surf.set_at((i, 15), _shift(surf.get_at((i, 15))[:3], -36))
        surf.set_at((15, i), _shift(surf.get_at((15, i))[:3], -28))


def pattern_speckles(rng: random.Random, color: tuple[int, int, int], accent: tuple[int, int, int]) -> pygame.Surface:
    surf = _surface()
    _fill_noise(surf, rng, color, 10)
    for _ in range(14):
        x, y = rng.randrange(1, 15), rng.randrange(1, 15)
        surf.set_at((x, y), accent)
        if rng.random() < 0.5:
            surf.set_at((x + 1, y), _shift(accent, 18))
    _bevel(surf)
    return surf


def pattern_pebbles(rng: random.Random, color: tuple[int, int, int], accent: tuple[int, int, int]) -> pygame.Surface:
    surf = _surface()
    _fill_noise(surf, rng, _shift(color, -18), 6)
    for _ in range(9):
        x, y = rng.randrange(1, 13), rng.randrange(1, 13)
        pebble = _shift(accent, rng.randint(-12, 16))
        surf.set_at((x, y), pebble)
        surf.set_at((x + 1, y), _shift(pebble, -20))
        surf.set_at((x, y + 1), _shift(pebble, 14))
        surf.set_at((x + 1, y + 1), _shift(pebble, -8))
    _bevel(surf)
    return surf


def pattern_cracks(rng: random.Random, color: tuple[int, int, int], accent: tuple[int, int, int]) -> pygame.Surface:
    surf = _surface()
    _fill_noise(surf, rng, color, 8)
    for _ in range(5):
        x, y = rng.randrange(16), rng.randrange(16)
        surf.set_at((x, y), _shift(color, 22))
    # Zwei kurze Risse, kein festes Muster aus einem anderen Spiel.
    for _ in range(2):
        x, y = rng.randrange(3, 12), rng.randrange(2, 8)
        for _step in range(6):
            surf.set_at((max(0, min(15, x)), max(0, min(15, y))), accent)
            x += rng.choice((-1, 0, 1))
            y += rng.choice((0, 1, 1))
    _bevel(surf)
    return surf


def pattern_ore(rng: random.Random, color: tuple[int, int, int], accent: tuple[int, int, int]) -> pygame.Surface:
    surf = _surface()
    _fill_noise(surf, rng, color, 8)
    for _ in range(4):
        x, y = rng.randrange(2, 13), rng.randrange(2, 13)
        for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1), (-1, 0)):
            px, py = x + dx, y + dy
            if 0 <= px < 16 and 0 <= py < 16 and rng.random() < 0.8:
                surf.set_at((px, py), _shift(accent, rng.randint(-10, 16)))
    _bevel(surf)
    return surf


def pattern_crystals(rng: random.Random, color: tuple[int, int, int], accent: tuple[int, int, int]) -> pygame.Surface:
    surf = _surface()
    _fill_noise(surf, rng, color, 7)
    shards = ((4, 11, 1), (8, 10, -1), (11, 12, 1), (6, 6, 1))
    for x, y, lean in shards:
        for step in range(5):
            px = x + lean * (step // 2)
            py = y - step
            if 0 <= px < 16 and 0 <= py < 16:
                surf.set_at((px, py), accent if step < 4 else _shift(accent, 40))
            if 0 <= px + 1 < 16 and 0 <= py < 16 and step % 2 == 0:
                surf.set_at((px + 1, py), _shift(accent, -30))
    _bevel(surf)
    return surf


def pattern_veins(rng: random.Random, color: tuple[int, int, int], accent: tuple[int, int, int]) -> pygame.Surface:
    surf = _surface()
    _fill_noise(surf, rng, color, 5)
    x, y = 1, rng.randrange(3, 8)
    for _ in range(18):
        if 0 <= x < 16 and 0 <= y < 16:
            surf.set_at((x, y), accent)
            if y + 1 < 16:
                surf.set_at((x, y + 1), _shift(accent, -24))
        x += rng.choice((1, 1, 0))
        y += rng.choice((-1, 0, 1))
    _bevel(surf)
    return surf


def pattern_charge(rng: random.Random, color: tuple[int, int, int], accent: tuple[int, int, int]) -> pygame.Surface:
    """Runde Ladung mit kurzer Zündschnur. Kein beschrifteter Klotz."""
    surf = _surface()
    _fill_noise(surf, rng, _shift(color, -8), 4)
    center = (8, 9)
    for y in range(16):
        for x in range(16):
            dist = (x - center[0]) ** 2 + (y - center[1]) ** 2
            if dist <= 22:
                surf.set_at((x, y), _shift(color, 12 if x < 8 else -8))
            if 16 <= dist <= 22:
                surf.set_at((x, y), _shift(color, -30))
    # Zündschnur nach oben, Funke am Ende.
    for y in range(2, 6):
        surf.set_at((8, y), (70, 58, 46))
        surf.set_at((9, y), (40, 32, 28))
    surf.set_at((8, 1), accent)
    surf.set_at((9, 1), _shift(accent, 30))
    surf.set_at((7, 2), _shift(accent, -20))
    _bevel(surf)
    return surf


_BUILDERS = {
    "speckles": pattern_speckles,
    "pebbles": pattern_pebbles,
    "cracks": pattern_cracks,
    "ore": pattern_ore,
    "crystals": pattern_crystals,
    "veins": pattern_veins,
    "charge": pattern_charge,
}


def build_pattern(pattern: str, color: tuple[int, int, int], accent: tuple[int, int, int], salt: int) -> pygame.Surface:
    builder = _BUILDERS.get(pattern, pattern_speckles)
    # Salt fest, damit Erde immer gleich aussieht, auch nach einem Neustart.
    rng = random.Random(10_000 + salt)
    return builder(rng, color, accent)


def build_pickaxe() -> pygame.Surface:
    """Kleine Spitzhacke, selbst gesetzt. Holzstiel, heller Kopf, dunkle Umrandung."""
    surf = _surface()
    outline = (36, 28, 26, 255)
    wood = (166, 116, 68, 255)
    wood_dark = (110, 72, 42, 255)
    metal = (226, 230, 234, 255)
    metal_dark = (128, 136, 146, 255)
    # Stiel von links unten nach rechts oben.
    for i in range(3, 12):
        surf.set_at((i, 14 - i), wood)
        surf.set_at((i + 1, 14 - i), wood_dark)
        surf.set_at((i, 15 - i), outline)
    # Kopf, quer dazu, mit zwei Spitzen.
    head = [
        (10, 2), (11, 2), (12, 3), (13, 4),
        (9, 3), (10, 3), (11, 3), (12, 4), (13, 5), (14, 6),
        (8, 4), (9, 4), (10, 4), (11, 4), (12, 5),
        (11, 5), (12, 6), (13, 7),
        (7, 5), (6, 6), (5, 7),
    ]
    for x, y in head:
        surf.set_at((x, y), metal)
    for x, y in ((10, 2), (5, 7), (14, 6), (13, 4)):
        surf.set_at((x, y), outline)
    surf.set_at((11, 3), metal_dark)
    surf.set_at((12, 4), metal_dark)
    return surf


def build_cracks_overlay() -> pygame.Surface:
    surf = _surface()
    dark = (20, 16, 18, 180)
    for x, y in ((3, 4), (4, 5), (5, 6), (6, 6), (8, 9), (9, 10), (10, 11), (11, 11), (7, 8)):
        surf.set_at((x, y), dark)
    return surf


class TextureAtlas:
    """16x16-Bilder, einmal auf Blockgröße skaliert."""

    def __init__(self, blocks: dict[str, BlockType], block_size: int, texture_dir: Path) -> None:
        self.block_size = block_size
        self.texture_dir = texture_dir
        texture_dir.mkdir(parents=True, exist_ok=True)
        self.images: dict[str, pygame.Surface] = {}
        self.flipped: dict[str, pygame.Surface] = {}
        salt = 1
        for block_id, spec in blocks.items():
            if spec.pattern == "none":
                continue
            image = self._load_or_make(block_id, spec, salt)
            scaled = nearest_scale(image, (block_size, block_size))
            self.images[block_id] = scaled
            self.flipped[block_id] = pygame.transform.flip(scaled, True, False)
            salt += 17
        pick = self._load_or_make_surface("pickaxe", build_pickaxe())
        self.pickaxe = nearest_scale(pick, (block_size, block_size))
        cracks = self._load_or_make_surface("cracks", build_cracks_overlay())
        self.cracks = nearest_scale(cracks, (block_size, block_size))

    def block(self, type_id: str, flip: bool) -> pygame.Surface | None:
        table = self.flipped if flip else self.images
        return table.get(type_id)

    def _load_or_make(self, block_id: str, spec: BlockType, salt: int) -> pygame.Surface:
        path = self.texture_dir / f"{block_id}.png"

        def make() -> pygame.Surface:
            return build_pattern(spec.pattern, spec.color, spec.accent, salt)

        return self._load_or_make_surface(block_id, make(), path)

    def _load_or_make_surface(
        self,
        name: str,
        generated: pygame.Surface,
        path: Path | None = None,
    ) -> pygame.Surface:
        file_path = path or (self.texture_dir / f"{name}.png")
        if file_path.exists():
            loaded = pygame.image.load(file_path).convert_alpha()
            if loaded.get_size() != (16, 16):
                loaded = pygame.transform.scale(loaded, (16, 16))
            return loaded
        pygame.image.save(generated, file_path)
        return generated
