"""Verbindet Höhle, Physik, Stimmen, Punkte und Ereignisse.

Diese Datei kennt kein Fenster. Sie rechnet nur. Das Zeichnen liegt in
render.py. Dadurch können Tests eine Runde durchrechnen, ohne SDL.
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass

from cave_dig.commands import parse_event_command
from cave_dig.config import GameConfig
from cave_dig.events import create_event
from cave_dig.events.base import CaveEvent
from cave_dig.i18n import Catalog, load_catalog
from cave_dig.languages import LanguageTable
from cave_dig.physics import Pickaxe
from cave_dig.scoring import (
    Scoreboard,
    load_scoreboard,
    points_at_depth,
    save_scoreboard,
    split_points,
)
from cave_dig.util import sanitize_name
from cave_dig.votes import VoteAggregator, VoteResult
from cave_dig.world import Destroyed, HitResult, World

log = logging.getLogger("cave_dig.game")

# Mehr Nachrichten heben wir für die nächste Runde nicht auf.
MAX_HELD_MESSAGES = 400


@dataclass
class ChatLine:
    """Eine Nachricht, wie sie von jedem Chat-Anbieter kommt."""

    author: str
    text: str
    sent_at: float = 0.0


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    color: tuple[int, int, int]
    size: int


@dataclass
class Floater:
    x: float
    y: float
    text: str
    life: float
    color: tuple[int, int, int]


class Game:
    def __init__(
        self,
        config: GameConfig,
        languages: LanguageTable,
        *,
        seed: int | None = None,
        demo: bool = False,
    ) -> None:
        self.config = config
        self.languages = languages
        self.catalog: Catalog = load_catalog(config.language, config.locales_dir)
        self.demo = demo
        self.time = 0.0
        self.phase = "play"
        self.phase_time = 0.0
        self.end_reason = ""
        self.last_round_score = 0
        self.last_round_depth = 0
        self.round_index = 0
        self.max_depth = 0
        self.camera_y = 0.0
        self.pending_points = 0
        self.local_direction = 0
        self.nudge_side: str | None = None
        self.nudge_timer = 0.0
        self.shake = 0.0
        self.status_line = ""
        self.pending_end: str | None = None
        self.event: CaveEvent | None = None
        self.event_ready_at = 0.0
        self.next_random_at = 0.0
        self.demo_event_done = False
        self.particles: list[Particle] = []
        self.floaters: list[Floater] = []
        self.explosion_queue: list[tuple[int, int]] = []
        self.since_progress = 0.0
        self.progress_mark = 0.0
        self.last_jolt = -100.0
        self.last_save = 0.0
        self.held_messages: list[ChatLine] = []
        chosen = config.world_seed if seed is None else seed
        self._seed_base = chosen
        self.rng = random.Random(1)
        self.fx_rng = random.Random(2)
        self.scoreboard: Scoreboard = load_scoreboard(config.save_path)
        self.votes = VoteAggregator(config.vote_window_seconds, config.one_vote_per_user)
        self.world = World(config, seed=1)
        self.pickaxe = self._make_pickaxe()
        self.start_round()

    def start_round(self) -> None:
        """Baut eine neue Höhle und setzt die Spitzhacke nach oben."""
        self.round_index += 1
        if self._seed_base:
            round_seed = (self._seed_base + self.round_index * 997) & 0x7FFFFFFF
        else:
            round_seed = random.SystemRandom().randrange(1, 2_000_000_000)
        self.rng = random.Random(round_seed)
        # Eigener Zufall für Funken. Der darf die Höhle nicht verändern,
        # wenn wir später mehr Partikel zeichnen.
        self.fx_rng = random.Random(round_seed ^ 0x51ED)
        self.world = World(self.config, round_seed)
        self.pickaxe = self._make_pickaxe()
        self.pickaxe.vx = self.rng.uniform(-40, 40)
        self.phase = "play"
        self.phase_time = 0.0
        self.pending_end = None
        self.pending_points = 0
        self.max_depth = 0
        self.camera_y = 0.0
        self.since_progress = 0.0
        self.progress_mark = self.pickaxe.y
        self.votes.reset(self.time)
        self.particles.clear()
        self.floaters.clear()
        self.explosion_queue.clear()
        self.event = None
        self.nudge_side = None
        self.nudge_timer = 0.0
        self.shake = 0.0
        wait = self.rng.uniform(self.config.random_min_seconds, self.config.random_max_seconds)
        self.next_random_at = self.time + wait
        self.world.ensure_through(self.config.sky_rows + 30)
        log.info("Runde %s beginnt (Seed %s).", self.round_index, round_seed)

    def handle_messages(self, messages: list[ChatLine]) -> None:
        """Chat darf das Spiel nicht abschießen. Jede Zeile ist in try verpackt.

        In der Rundenpause heben wir Nachrichten auf. Der Anbieter gibt jede
        Nachricht nur einmal her, und YouTube liefert sie selten.
        """
        if self.phase != "play":
            self.held_messages.extend(messages)
            del self.held_messages[:-MAX_HELD_MESSAGES]
            return
        for message in messages:
            try:
                self._handle_one(message)
            except Exception:
                log.exception("Chatnachricht übersprungen: %r", getattr(message, "text", message))

    def handle_local_vote(self, direction: str) -> None:
        """Taste beim Testen. Zählt wie ein Zuschauer namens 'Lokal'."""
        if self.phase != "play":
            return
        if direction not in ("left", "right"):
            return
        self._cast_vote(self.config.local_voter_name, direction)

    def update(self, dt: float) -> None:
        # Ein Hänger soll nicht eine Sekunde Physik auf einmal rechnen.
        # Sonst fällt die Spitzhacke durch Blöcke hindurch.
        if dt < 0:
            return
        dt = min(dt, 0.05)
        self.time += dt
        self.nudge_timer = max(0.0, self.nudge_timer - dt)
        self.shake = max(0.0, self.shake - 14 * dt)

        if self.phase == "ended":
            self.phase_time += dt
            self._update_particles(dt)
            if self.phase_time >= self.config.round_end_pause:
                self.start_round()
                held, self.held_messages = self.held_messages, []
                self.handle_messages(held)
            return

        for result in self.votes.close_due(self.time):
            self._apply_votes(result)
        if self.local_direction:
            sign = -1 if self.local_direction < 0 else 1
            self.pickaxe.vx += sign * self.config.local_steer * dt
        self.pickaxe.step(dt, self.world, self.on_contact)
        self._process_explosions()
        self._after_physics(dt)
        if self.event is not None and not self.event.done:
            try:
                self.event.on_update(self, dt)
            except Exception:
                log.exception("Ereignis %s in on_update abgebrochen.", self.event.id)
                self.event.done = True
        self._maybe_random_event()
        self._maybe_demo_event()
        self._update_camera(dt)
        self._update_particles(dt)
        depth_row = int(self.pickaxe.y / self.config.block_size)
        self.world.ensure_through(depth_row + self.config.logical_height // self.config.block_size + 4)
        self.world.discard_above(depth_row - 100)
        if self.time - self.last_save > 20:
            self.save()
            self.last_save = self.time

    def on_contact(self, col: int, row: int) -> bool:
        result = self.world.touch(col, row, self.time, self.config.hit_cooldown)
        if result is None:
            return False
        spec = self.config.blocks.get(result.type_id)
        color = spec.color if spec is not None else (180, 180, 180)
        self.spawn_burst(
            (col + 0.5) * self.config.block_size,
            (row + 0.5) * self.config.block_size,
            color,
            4 if not result.broken else 8,
        )
        if result.unbreakable:
            self.pickaxe.integrity -= self.config.bedrock_damage
            self._note_integrity()
            return False
        self.pickaxe.integrity -= self.config.chip_damage
        if result.broken:
            self._award_break(result.points, result.col, result.row, color)
            if result.explosive:
                self.explosion_queue.append((result.col, result.row))
            self._note_integrity()
            return True
        self._note_integrity()
        return False

    def queue_explosion(self, col: int, row: int) -> None:
        self.explosion_queue.append((col, row))

    def spawn_burst(
        self,
        x: float,
        y: float,
        color: tuple[int, int, int],
        count: int,
    ) -> None:
        for _ in range(count):
            if len(self.particles) > 240:
                self.particles.pop(0)
            angle = self.fx_rng.random() * math.tau
            speed = self.fx_rng.uniform(30, 160)
            life = self.fx_rng.uniform(0.25, 0.7)
            self.particles.append(
                Particle(
                    x=x,
                    y=y,
                    vx=math.cos(angle) * speed,
                    vy=math.sin(angle) * speed - 40,
                    life=life,
                    max_life=life,
                    color=color,
                    size=self.fx_rng.choice((2, 3, 4)),
                )
            )

    def save(self) -> None:
        try:
            save_scoreboard(self.config.save_path, self.scoreboard)
        except OSError as exc:
            log.warning("Speichern fehlgeschlagen: %s", exc)

    @property
    def block_size(self) -> int:
        return self.config.block_size

    def depth_meters(self) -> int:
        row = int(self.pickaxe.y / self.config.block_size) - self.config.sky_rows
        return max(0, row)

    def light_scale(self) -> float:
        if self.event is not None and not self.event.done:
            return self.event.light_scale()
        return 1.0

    def event_title(self) -> str | None:
        """Banner-Text aus der Sprachdatei, nicht der interne Id-Name."""
        if self.event is not None and not self.event.done:
            return self.catalog.t(f"events.{self.event.id}")
        return None

    def _handle_one(self, message: ChatLine) -> None:
        text = message.text if isinstance(message.text, str) else ""
        author = sanitize_name(message.author, self.catalog.t("hud.unknown"))
        command = parse_event_command(text, self.config.event_command, self.config.event_aliases)
        if command is not None:
            if command.unknown:
                # debug statt info: Chat-Spam soll das Log nicht füllen, und
                # sanitize_name nimmt Steuerzeichen aus dem fremden Text.
                log.debug(
                    "Unbekanntes Ereignis '%s' von %s, ignoriert.",
                    sanitize_name(command.unknown),
                    author,
                )
                return
            started = self.start_event(command.event_id)
            if not started:
                log.debug("Ereignis von %s liegt in der Abklingzeit oder läuft schon.", author)
            return
        direction = self.languages.parse(text)
        if direction is None:
            return
        self._cast_vote(author, direction)

    def _cast_vote(self, author: str, direction: str) -> None:
        closed = self.votes.add(author, direction, self.time)
        for result in closed:
            self._apply_votes(result)

    def start_event(self, event_id: str | None, *, force: bool = False) -> bool:
        if self.phase != "play":
            return False
        if self.event is not None and not self.event.done:
            return False
        if not force and self.time < self.event_ready_at:
            return False
        if event_id is None:
            if not self.config.event_ids:
                return False
            event_id = self.rng.choice(list(self.config.event_ids))
        event = create_event(event_id, self.config)
        if event is None:
            log.info("Ereignis '%s' ist nicht registriert.", event_id)
            return False
        try:
            event.on_start(self)
        except Exception:
            log.exception("Ereignis %s in on_start abgebrochen.", event_id)
            return False
        self.event = event
        self.event_ready_at = self.time + self.config.event_cooldown
        self._note_integrity()
        log.info("Ereignis gestartet: %s", self.catalog.t(f"events.{event.id}"))
        return True

    def _apply_votes(self, result: VoteResult) -> None:
        credited = result.credit_names()
        shares = split_points(self.pending_points, credited)
        for name, points in shares.items():
            self.scoreboard.add_contributor_points(name, points)
        for name in result.all_voters():
            self.scoreboard.add_vote(name)
        # Ein leeres Fenster behält die Punkte für die nächsten Stimmen.
        # YouTube liefert nur alle 50 Sekunden, die meisten Fenster sind leer.
        if credited:
            self.pending_points = 0
        if result.winner is None:
            self.nudge_side = None
            self.nudge_timer = 0.45
            return
        sign = -1 if result.winner == "left" else 1
        total = result.left + result.right
        margin = abs(result.left - result.right) / total if total else 0
        impulse = self.config.nudge_speed * (0.45 + 0.55 * margin)
        self.pickaxe.vx += sign * impulse
        limit = self.config.max_horizontal_speed
        if self.pickaxe.vx > limit:
            self.pickaxe.vx = limit
        elif self.pickaxe.vx < -limit:
            self.pickaxe.vx = -limit
        self.nudge_side = result.winner
        self.nudge_timer = 0.7

    def _award_break(self, base_points: int, col: int, row: int, color: tuple[int, int, int]) -> None:
        points = points_at_depth(
            base_points,
            self.depth_meters(),
            self.config.depth_bonus_per_meter,
            self.config.depth_bonus_cap,
        )
        if points <= 0:
            return
        self.scoreboard.add_round_points(points)
        self.pending_points += points
        if len(self.floaters) > 16:
            self.floaters.pop(0)
        self.floaters.append(
            Floater(
                x=(col + 0.5) * self.config.block_size,
                y=(row + 0.3) * self.config.block_size,
                text=f"+{points}",
                life=0.9,
                color=color,
            )
        )

    def _award_destroyed(self, destroyed: Destroyed, col: int, row: int) -> None:
        self._award_break(destroyed.points, col, row, destroyed.color)
        self.spawn_burst(
            (col + 0.5) * self.config.block_size,
            (row + 0.5) * self.config.block_size,
            destroyed.color,
            6,
        )

    def _process_explosions(self) -> None:
        seen: set[tuple[int, int]] = set()
        guard = 0
        while self.explosion_queue and guard < 20:
            guard += 1
            col, row = self.explosion_queue.pop(0)
            if (col, row) in seen:
                continue
            seen.add((col, row))
            self._detonate(col, row, seen)

    def _detonate(self, col: int, row: int, seen: set[tuple[int, int]]) -> None:
        radius = self.config.explosion_radius
        reach = int(radius) + 1
        for dc in range(-reach, reach + 1):
            for dr in range(-reach, reach + 1):
                if dc * dc + dr * dr > radius * radius:
                    continue
                destroyed = self.world.destroy(col + dc, row + dr)
                if destroyed is None:
                    continue
                self._award_destroyed(destroyed, col + dc, row + dr)
                if destroyed.explosive:
                    nxt = (col + dc, row + dr)
                    if nxt not in seen:
                        self.explosion_queue.append(nxt)
        center_x = (col + 0.5) * self.config.block_size
        center_y = (row + 0.5) * self.config.block_size
        self.spawn_burst(center_x, center_y, (230, 150, 60), 18)
        self.shake = max(self.shake, 10)
        distance = math.hypot(self.pickaxe.x - center_x, self.pickaxe.y - center_y)
        reach_px = self.config.block_size * 3.3
        if distance < reach_px:
            falloff = 1.0 - distance / reach_px
            self.pickaxe.integrity -= self.config.explosion_damage * falloff
            self._note_integrity()

    def _after_physics(self, dt: float) -> None:
        self.pickaxe.integrity -= self.config.passive_drain * dt
        if self.pickaxe.vy > self.config.regen_min_speed:
            self.pickaxe.integrity += self.config.regen_per_second * dt
        maximum = self.config.integrity_max
        if self.pickaxe.integrity > maximum:
            self.pickaxe.integrity = maximum
        self.max_depth = max(self.max_depth, self.depth_meters())
        if self.pickaxe.y > self.progress_mark + 12:
            self.progress_mark = self.pickaxe.y
            self.since_progress = 0.0
        else:
            self.since_progress += dt
        if self.since_progress > 3.5 and self.time - self.last_jolt > 1.6:
            self.last_jolt = self.time
            self.pickaxe.vx += self.rng.choice((-240.0, 240.0))
            self.pickaxe.vy = max(self.pickaxe.vy, 70.0)
            self.shake = max(self.shake, 3.0)
        if self.since_progress > self.config.stuck_seconds:
            self.pending_end = "round.stuck"
        self._note_integrity()
        if self.pending_end:
            self._end_round(self.pending_end)

    def _note_integrity(self) -> None:
        if self.pickaxe.integrity <= 0 and self.pending_end is None and self.phase == "play":
            self.pickaxe.integrity = 0
            self.pending_end = "round.broken"

    def _end_round(self, reason: str) -> None:
        if self.phase == "ended":
            return
        # Das offene Fenster noch auszählen, sonst gehen die letzten Punkte verloren.
        if self.votes.entries:
            self._apply_votes(self.votes.close_now())
        self.phase = "ended"
        self.phase_time = 0.0
        self.end_reason = reason
        self.last_round_score = self.scoreboard.round_score
        self.last_round_depth = self.max_depth
        self.scoreboard.finish_round(self.max_depth)
        self.pending_end = None
        self.save()
        self.last_save = self.time
        log.info(
            "Runde %s vorbei (%s). Punkte %s, Tiefe %s m.",
            self.round_index,
            self.catalog.t(reason),
            self.last_round_score,
            self.last_round_depth,
        )

    def _maybe_random_event(self) -> None:
        if self.demo or not self.config.events_enabled:
            return
        if self.time < self.next_random_at:
            return
        span = self.rng.uniform(self.config.random_min_seconds, self.config.random_max_seconds)
        self.next_random_at = self.time + span
        if self.rng.random() <= self.config.random_chance:
            self.start_event(None)

    def _maybe_demo_event(self) -> None:
        """Für Screenshots: eine Erzader, sobald die Spitzhacke in der Höhle ist."""
        if not self.demo or self.demo_event_done or self.time < 3.15:
            return
        self.demo_event_done = True
        self.start_event("ore_vein", force=True)

    def _update_camera(self, dt: float) -> None:
        target = self.pickaxe.y - self.config.logical_height * 0.40
        if target < 0:
            target = 0
        # Weiches Nachziehen. 1 - exp(-k*dt) ist unabhängig von der Bildrate.
        blend = 1.0 - math.exp(-4.2 * dt)
        self.camera_y += (target - self.camera_y) * blend

    def _update_particles(self, dt: float) -> None:
        alive: list[Particle] = []
        for particle in self.particles:
            particle.life -= dt
            if particle.life <= 0:
                continue
            particle.vy += 280 * dt
            particle.x += particle.vx * dt
            particle.y += particle.vy * dt
            alive.append(particle)
        self.particles = alive
        floating: list[Floater] = []
        for floater in self.floaters:
            floater.life -= dt
            floater.y -= 28 * dt
            if floater.life > 0:
                floating.append(floater)
        self.floaters = floating

    def _make_pickaxe(self) -> Pickaxe:
        config = self.config
        x = config.columns * config.block_size * 0.5
        y = config.block_size * 1.4
        return Pickaxe(
            x=x,
            y=y,
            vx=0.0,
            vy=30.0,
            radius=config.pickaxe_radius,
            integrity=config.integrity_max,
            gravity=config.gravity,
            max_fall=config.max_fall,
            restitution=config.restitution,
            horizontal_drag=config.horizontal_drag,
            max_horizontal_speed=config.max_horizontal_speed,
        )
