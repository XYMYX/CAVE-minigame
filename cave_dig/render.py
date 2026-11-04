"""Zeichnet die Höhle und die Anzeigen.

Die innere Fläche ist zum Beispiel 540x960. Das Fenster ist doppelt so groß.
Wir malen klein und vergrößern danach auf Pixelkanten, damit OBS ein scharfes
9:16-Bild bekommt und die Blöcke kantig bleiben.

Reihenfolge: Höhle, Licht, dann die Leiste. Die Leiste liegt immer oben auf,
auch wenn die Lampe klein ist.
"""

from __future__ import annotations

import math
import random

import pygame

from cave_dig.config import GameConfig
from cave_dig.fonts import FontBook
from cave_dig.game import Game
from cave_dig.textures import TextureAtlas, nearest_scale
from cave_dig.util import format_int, lerp_color


class Renderer:
    def __init__(
        self,
        config: GameConfig,
        fonts: FontBook,
        textures: TextureAtlas,
    ) -> None:
        self.config = config
        self.fonts = fonts
        self.textures = textures
        self.fx = random.Random(1)
        width = config.logical_width
        height = config.logical_height
        self.dark = pygame.Surface((width, height), pygame.SRCALPHA)
        self.vignette = _make_vignette(width, height)
        self.light = _make_light(400)
        self._light_cache: dict[int, pygame.Surface] = {400: self.light}
        self.panel = pygame.Surface((width - 24, 10), pygame.SRCALPHA)

    def draw(self, target: pygame.Surface, game: Game) -> None:
        config = self.config
        depth_t = min(1.0, game.depth_meters() / 380)
        background = lerp_color(
            config.colors["background_top"],
            config.colors["background_deep"],
            depth_t,
        )
        target.fill(background)
        shake_x, shake_y = self._shake(game)
        self._draw_blocks(target, game, shake_x, shake_y)
        self._draw_particles(target, game, shake_x, shake_y)
        self._draw_pickaxe(target, game, shake_x, shake_y)
        self._draw_light(target, game, shake_x, shake_y)
        target.blit(self.vignette, (0, 0))
        self._draw_floaters(target, game, shake_x, shake_y)
        self._draw_nudge(target, game)
        self._draw_hud(target, game)
        if game.phase == "ended":
            self._draw_round_end(target, game)

    def _shake(self, game: Game) -> tuple[int, int]:
        magnitude = int(game.shake)
        if magnitude < 1:
            return 0, 0
        return self.fx.randint(-magnitude, magnitude), self.fx.randint(-magnitude, magnitude)

    def _draw_blocks(self, target: pygame.Surface, game: Game, ox: int, oy: int) -> None:
        size = self.config.block_size
        height = self.config.logical_height
        first = max(0, int(game.camera_y // size) - 1)
        last = int((game.camera_y + height) // size) + 2
        game.world.ensure_through(last)
        for row in range(first, last + 1):
            y = row * size - game.camera_y + oy
            if y > height or y + size < 0:
                continue
            for col in range(self.config.columns):
                block = game.world.block_at(col, row)
                if block is None or block.type_id == "air":
                    continue
                image = self.textures.block(block.type_id, ((col * 3 + row) & 1) == 0)
                if image is None:
                    continue
                x = col * size + ox
                target.blit(image, (x, y))
                spec = self.config.blocks.get(block.type_id)
                if (
                    spec is not None
                    and not spec.unbreakable
                    and block.max_hp > 1
                    and block.hp < block.max_hp
                ):
                    target.blit(self.textures.cracks, (x, y))

    def _draw_particles(self, target: pygame.Surface, game: Game, ox: int, oy: int) -> None:
        for particle in game.particles:
            x = int(particle.x + ox)
            y = int(particle.y - game.camera_y + oy)
            fade = particle.life / particle.max_life if particle.max_life else 0
            if fade <= 0:
                continue
            color = tuple(int(channel * (0.45 + 0.55 * fade)) for channel in particle.color)
            pygame.draw.rect(target, color, (x, y, particle.size, particle.size))

    def _draw_pickaxe(self, target: pygame.Surface, game: Game, ox: int, oy: int) -> None:
        limit = self.config.max_horizontal_speed or 1
        lean = max(-1.0, min(1.0, game.pickaxe.vx / limit)) * 32
        key = int(round(lean / 8.0)) * 8
        rotated = self._rotated_pick(key)
        cx = int(game.pickaxe.x + ox)
        cy = int(game.pickaxe.y - game.camera_y + oy)
        # Dunkler Fleck dahinter, sonst verschwindet der Kopf im Gestein.
        pygame.draw.circle(target, (28, 18, 16), (cx, cy), int(self.config.pickaxe_radius) + 4)
        target.blit(rotated, (cx - rotated.get_width() // 2, cy - rotated.get_height() // 2))

    def _rotated_pick(self, angle: int) -> pygame.Surface:
        cache = getattr(self, "_pick_cache", None)
        if cache is None:
            cache = {}
            self._pick_cache = cache
        image = cache.get(angle)
        if image is None:
            image = pygame.transform.rotate(self.textures.pickaxe, angle)
            cache[angle] = image
        return image

    def _draw_light(self, target: pygame.Surface, game: Game, ox: int, oy: int) -> None:
        flicker = 0.94 + 0.06 * math.sin(game.time * 8.0)
        scale = max(0.22, flicker * game.light_scale())
        diameter = max(24, int(400 * scale))
        # Auf gerade Zahlen runden, damit der Cache klein bleibt.
        diameter -= diameter % 4
        light = self._light_cache.get(diameter)
        if light is None:
            light = nearest_scale(self.light, (diameter, diameter))
            self._light_cache[diameter] = light
        # Nicht pechschwarz: ein Stream zerdrückt sehr dunkle Bilder.
        alpha = 115 if scale > 0.7 else 170
        # Die Id, nicht der übersetzte Name. Sonst bleibt es bei "Darkness" hell.
        if game.event is not None and not game.event.done and game.event.id == "darkness":
            alpha = 205
        self.dark.fill((0, 0, 0, alpha))
        x = int(game.pickaxe.x + ox - diameter / 2)
        y = int(game.pickaxe.y - game.camera_y + oy - diameter / 2)
        self.dark.blit(light, (x, y), special_flags=pygame.BLEND_RGBA_SUB)
        target.blit(self.dark, (0, 0))

    def _draw_floaters(self, target: pygame.Surface, game: Game, ox: int, oy: int) -> None:
        for floater in game.floaters:
            image = self.fonts.render(floater.text, 16, floater.color)
            x = int(floater.x + ox - image.get_width() / 2)
            y = int(floater.y - game.camera_y + oy)
            target.blit(image, (x, y))

    def _draw_nudge(self, target: pygame.Surface, game: Game) -> None:
        if game.nudge_timer <= 0 or game.nudge_side is None:
            return
        color = self.config.colors["left"] if game.nudge_side == "left" else self.config.colors["right"]
        alpha = int(180 * min(1.0, game.nudge_timer / 0.7))
        surf = pygame.Surface((70, 90), pygame.SRCALPHA)
        if game.nudge_side == "left":
            points = [(58, 8), (14, 45), (58, 82), (46, 45)]
            pos = (18, self.config.logical_height // 2 - 45)
        else:
            points = [(12, 8), (56, 45), (12, 82), (24, 45)]
            pos = (self.config.logical_width - 88, self.config.logical_height // 2 - 45)
        pygame.draw.polygon(surf, (*color, alpha), points)
        target.blit(surf, pos)

    def _draw_hud(self, target: pygame.Surface, game: Game) -> None:
        colors = self.config.colors
        width = self.config.logical_width
        top = self._panel(width - 20, 188)
        target.blit(top, (10, 8))
        text = game.catalog
        title = self.fonts.render_shadow(self.config.title.upper(), 22, colors["accent"])
        target.blit(title, (22, 16))
        round_label = self.fonts.render(text.t("hud.round", n=game.round_index), 16, colors["muted"])
        target.blit(round_label, (width - 22 - round_label.get_width(), 20))

        self._stat(
            target,
            22,
            42,
            text.t("hud.depth"),
            text.t("hud.meters", n=format_int(game.depth_meters())),
            colors,
        )
        self._stat(
            target,
            width // 2 + 8,
            42,
            text.t("hud.score"),
            format_int(game.scoreboard.round_score),
            colors,
        )
        record = self.fonts.render(
            text.t(
                "hud.record",
                score=format_int(game.scoreboard.high_score),
                depth=format_int(game.scoreboard.best_depth),
            ),
            14,
            colors["muted"],
        )
        target.blit(record, (22, 96))
        self._integrity(target, game, 22, 118)
        self._vote_bar(target, game, 22, 140)

        bottom_h = 196
        bottom = self._panel(width - 20, bottom_h)
        target.blit(bottom, (10, self.config.logical_height - bottom_h - 10))
        y = self.config.logical_height - bottom_h
        text = game.catalog
        hint = self._hint(game)
        hint_image = self.fonts.render(hint, 16, colors["text"])
        target.blit(hint_image, (22, y + 8))
        header = self.fonts.render(text.t("hud.miners"), 16, colors["accent"])
        target.blit(header, (22, y + 32))
        header_right = self.fonts.render(text.t("hud.points_votes"), 14, colors["muted"])
        target.blit(header_right, (width - 22 - header_right.get_width(), y + 34))
        rows = game.scoreboard.top(4)
        if not rows:
            empty = self.fonts.render(text.t("hud.empty"), 15, colors["muted"])
            target.blit(empty, (22, y + 58))
        else:
            for index, entry in enumerate(rows):
                line = self.fonts.render(
                    f"{index + 1}  {entry.name}",
                    16,
                    colors["text"],
                )
                points = self.fonts.render(
                    f"{format_int(entry.points)}   {entry.votes}",
                    16,
                    colors["accent"],
                )
                line_y = y + 56 + index * 24
                target.blit(line, (22, line_y))
                target.blit(points, (width - 22 - points.get_width(), line_y))
        if self.config.show_status and game.status_line:
            # Mehrere Chat-Quellen ergeben mehrere Zeilen, die letzte steht unten.
            for index, text in enumerate(reversed(game.status_line.split("\n"))):
                status = self.fonts.render(text, 13, colors["muted"])
                target.blit(status, (22, self.config.logical_height - 28 - index * 18))

        banner = game.event_title()
        if banner and game.phase == "play":
            self._banner(target, banner, colors["accent"])

    def _stat(
        self,
        target: pygame.Surface,
        x: int,
        y: int,
        label: str,
        value: str,
        colors: dict[str, tuple[int, int, int]],
    ) -> None:
        lab = self.fonts.render(label, 14, colors["muted"])
        val = self.fonts.render_shadow(value, 28, colors["text"])
        target.blit(lab, (x, y))
        target.blit(val, (x, y + 16))

    def _integrity(self, target: pygame.Surface, game: Game, x: int, y: int) -> None:
        colors = self.config.colors
        ratio = 0.0
        if self.config.integrity_max:
            ratio = max(0.0, min(1.0, game.pickaxe.integrity / self.config.integrity_max))
        label = self.fonts.render(game.catalog.t("hud.pickaxe"), 13, colors["muted"])
        target.blit(label, (x, y - 2))
        bar_x = x + 78
        bar_w = self.config.logical_width - bar_x - 28
        pygame.draw.rect(target, (40, 32, 36), (bar_x, y, bar_w, 10))
        fill = colors["good"] if ratio > 0.35 else colors["danger"]
        pygame.draw.rect(target, fill, (bar_x, y, int(bar_w * ratio), 10))

    def _vote_bar(self, target: pygame.Surface, game: Game, x: int, y: int) -> None:
        """Balken von links nach rechts. Darunter eine dünne Uhr bis zur Auszählung."""
        colors = self.config.colors
        width = self.config.logical_width - 44
        left = game.votes.left
        right = game.votes.right
        total = left + right
        text = game.catalog
        left_text = self.fonts.render(text.t("hud.votes_left", count=left), 13, colors["left"])
        right_text = self.fonts.render(text.t("hud.votes_right", count=right), 13, colors["right"])
        target.blit(left_text, (x, y))
        target.blit(right_text, (x + width - right_text.get_width(), y))
        # Abstand, damit die Wörter nicht auf dem Balken liegen.
        bar_y = y + 18
        pygame.draw.rect(target, (36, 28, 32), (x, bar_y, width, 12))
        if total:
            left_w = int(width * left / total)
            pygame.draw.rect(target, colors["left"], (x, bar_y, left_w, 12))
            pygame.draw.rect(target, colors["right"], (x + left_w, bar_y, width - left_w, 12))
        mid = x + width // 2
        pygame.draw.line(target, colors["text"], (mid, bar_y - 1), (mid, bar_y + 13), 2)
        progress = game.votes.progress(game.time)
        pygame.draw.rect(target, colors["accent"], (x, bar_y + 13, int(width * progress), 3))

    def _hint(self, game: Game) -> str:
        hints = game.languages.hints
        if not hints:
            return game.catalog.t("hud.hint_fallback")
        index = int(game.time / self.config.hint_seconds) % len(hints)
        return game.catalog.t("hud.hint", hint=hints[index])

    def _banner(self, target: pygame.Surface, text: str, color: tuple[int, int, int]) -> None:
        image = self.fonts.render_shadow(text, 26, color)
        x = (self.config.logical_width - image.get_width()) // 2
        y = 198
        pad = pygame.Surface((image.get_width() + 24, image.get_height() + 10), pygame.SRCALPHA)
        pad.fill((8, 6, 10, 170))
        target.blit(pad, (x - 12, y - 4))
        target.blit(image, (x, y))

    def _draw_round_end(self, target: pygame.Surface, game: Game) -> None:
        colors = self.config.colors
        shade = pygame.Surface(target.get_size(), pygame.SRCALPHA)
        shade.fill((6, 4, 8, 170))
        target.blit(shade, (0, 0))
        text = game.catalog
        title = self.fonts.render_shadow(text.t("round.over"), 32, colors["accent"])
        reason = self.fonts.render(text.t(game.end_reason), 18, colors["text"])
        score = self.fonts.render_shadow(
            text.t("round.score", score=format_int(game.last_round_score)),
            28,
            colors["text"],
        )
        depth = self.fonts.render(
            text.t("round.depth", depth=format_int(game.last_round_depth)),
            18,
            colors["muted"],
        )
        nxt = self.fonts.render(text.t("round.next"), 16, colors["muted"])
        cx = self.config.logical_width // 2
        cy = self.config.logical_height // 2 - 40
        for image, extra in (
            (title, 0),
            (reason, 48),
            (score, 84),
            (depth, 124),
            (nxt, 160),
        ):
            target.blit(image, (cx - image.get_width() // 2, cy + extra))

    def _panel(self, width: int, height: int) -> pygame.Surface:
        key = (width, height)
        cache = getattr(self, "_panels", None)
        if cache is None:
            cache = {}
            self._panels = cache
        image = cache.get(key)
        if image is None:
            image = pygame.Surface((width, height), pygame.SRCALPHA)
            image.fill((10, 8, 12, 188))
            pygame.draw.rect(image, self.config.colors["accent"], image.get_rect(), 1)
            cache[key] = image
        return image


def _make_light(diameter: int) -> pygame.Surface:
    image = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
    center = diameter / 2
    for y in range(diameter):
        for x in range(diameter):
            dist = math.hypot(x - center, y - center) / center
            if dist >= 1:
                alpha = 0
            else:
                alpha = int(255 * (1 - dist) ** 1.45)
            image.set_at((x, y), (255, 255, 255, alpha))
    return image


def _make_vignette(width: int, height: int) -> pygame.Surface:
    image = pygame.Surface((width, height), pygame.SRCALPHA)
    bands = 70
    for i in range(bands):
        alpha = int(150 * (1 - i / bands) ** 1.6)
        pygame.draw.rect(
            image,
            (0, 0, 0, alpha),
            (i, i, width - 2 * i, height - 2 * i),
            1,
        )
    return image


def present(
    window: pygame.Surface,
    logical: pygame.Surface,
    background: tuple[int, int, int],
) -> None:
    """Kopiert die innere Fläche ins Fenster, Seitenverhältnis bleibt 9:16."""
    win_w, win_h = window.get_size()
    log_w, log_h = logical.get_size()
    scale = min(win_w / log_w, win_h / log_h)
    # transform.scale läuft in C. nearest_scale wäre hier pro Bild zu langsam,
    # die innere Fläche ist ja schon aus klaren Pixeln gebaut.
    if scale >= 1 and abs(scale - round(scale)) < 0.02 and abs(win_w / log_w - win_h / log_h) < 0.02:
        factor = int(round(scale))
        scaled = pygame.transform.scale(logical, (log_w * factor, log_h * factor))
        window.blit(scaled, (0, 0))
        return
    draw_w = max(1, int(log_w * scale))
    draw_h = max(1, int(log_h * scale))
    scaled = pygame.transform.scale(logical, (draw_w, draw_h))
    window.fill(background)
    window.blit(scaled, ((win_w - draw_w) // 2, (win_h - draw_h) // 2))
