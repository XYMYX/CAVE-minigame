"""Fall und Abprall der Spitzhacke.

Die Spitzhacke ist ein Kreis. Blöcke sind Kästchen. Pro Bild bewegen wir
uns in kleinen Schritten, damit sie bei hohem Tempo nicht durch einen
Block hindurchrutscht. Das ist derselbe Gedanke wie ein fester Zeitschritt
in einer C++-Physik, nur an die Bildrate gekoppelt und in Teilschritte
zerlegt.

on_contact bekommt Spalte und Reihe und sagt True, wenn der Block dabei
zerbricht. Zerbrochene Blöcke halten nicht auf. Ganze Blöcke schieben den
Kreis heraus und werfen die Geschwindigkeit zurück.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from cave_dig.world import World


@dataclass
class Pickaxe:
    x: float
    y: float
    vx: float
    vy: float
    radius: float
    integrity: float

    gravity: float
    max_fall: float
    restitution: float
    horizontal_drag: float
    max_horizontal_speed: float

    def step(
        self,
        dt: float,
        world: World,
        on_contact: Callable[[int, int], bool],
    ) -> None:
        if dt <= 0:
            return
        self.vy = min(self.max_fall, self.vy + self.gravity * dt)
        # exp(-d * dt) ist ein Tempo-Verlust, der nicht von der Bildrate abhängt.
        self.vx *= math.exp(-self.horizontal_drag * dt)
        self.vx = _clamp(self.vx, -self.max_horizontal_speed, self.max_horizontal_speed)

        speed = math.hypot(self.vx, self.vy)
        # Höchstens ein Viertel Block pro Teilschritt.
        limit = max(4.0, world.block_size * 0.25)
        steps = max(1, min(8, int(math.ceil(speed * dt / limit))))
        sub = dt / steps
        for _ in range(steps):
            self.x += self.vx * sub
            self._resolve(world, on_contact)
            self.y += self.vy * sub
            self._resolve(world, on_contact)
            self._keep_inside(world)

    def _resolve(self, world: World, on_contact: Callable[[int, int], bool]) -> None:
        for _ in range(6):
            hit = _deepest(self.x, self.y, self.radius, world)
            if hit is None:
                return
            col, row, nx, ny, pen = hit
            broken = on_contact(col, row)
            if broken:
                continue
            self.x += nx * (pen + 0.08)
            self.y += ny * (pen + 0.08)
            into = self.vx * nx + self.vy * ny
            if into < 0:
                bounce = 1.0 + self.restitution
                self.vx -= bounce * into * nx
                self.vy -= bounce * into * ny
                # Ein bisschen Reibung entlang der Kante, sonst rutscht sie ewig.
                tx, ty = -ny, nx
                tangent = self.vx * tx + self.vy * ty
                self.vx -= tangent * 0.18 * tx
                self.vy -= tangent * 0.18 * ty

    def _keep_inside(self, world: World) -> None:
        margin = self.radius + 1
        max_x = world.cols * world.block_size - margin
        if self.x < margin:
            self.x = margin
            self.vx = abs(self.vx) * 0.5
        elif self.x > max_x:
            self.x = max_x
            self.vx = -abs(self.vx) * 0.5


def _deepest(
    cx: float,
    cy: float,
    radius: float,
    world: World,
) -> tuple[int, int, float, float, float] | None:
    size = world.block_size
    min_col = int((cx - radius) // size) - 1
    max_col = int((cx + radius) // size) + 1
    min_row = int((cy - radius) // size) - 1
    max_row = int((cy + radius) // size) + 1
    best: tuple[int, int, float, float, float] | None = None
    for col in range(min_col, max_col + 1):
        for row in range(min_row, max_row + 1):
            if not world.is_solid(col, row):
                continue
            pen = _penetration(cx, cy, radius, world.rect(col, row))
            if pen is None:
                continue
            nx, ny, depth = pen
            if best is None or depth > best[4]:
                best = (col, row, nx, ny, depth)
    return best


def _penetration(
    cx: float,
    cy: float,
    radius: float,
    rect: tuple[float, float, float, float],
) -> tuple[float, float, float] | None:
    x, y, w, h = rect
    closest_x = min(max(cx, x), x + w)
    closest_y = min(max(cy, y), y + h)
    dx = cx - closest_x
    dy = cy - closest_y
    dist_sq = dx * dx + dy * dy
    if dist_sq >= radius * radius and dist_sq > 1e-8:
        return None
    if dist_sq > 1e-8:
        dist = math.sqrt(dist_sq)
        return dx / dist, dy / dist, radius - dist
    # Der Mittelpunkt liegt im Kästchen. Hinaus schieben, und zwar
    # über die nächste Kante.
    left = cx - x
    right = x + w - cx
    top = cy - y
    bottom = y + h - cy
    smallest = min(left, right, top, bottom)
    if smallest == left:
        return -1.0, 0.0, radius + left
    if smallest == right:
        return 1.0, 0.0, radius + right
    if smallest == top:
        return 0.0, -1.0, radius + top
    return 0.0, 1.0, radius + bottom


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
