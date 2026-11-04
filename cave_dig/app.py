"""Fenster, Spielschleife, Tastatur.

Die Schleife ist dasselbe Muster wie in C++ mit SDL oder SFML:

    solange das Fenster offen ist:
        Eingaben lesen
        Welt um dt Sekunden weiterschieben
        alles zeichnen

dt ist die Zeit seit dem letzten Bild. Bei 60 Bildern pro Sekunde ist dt
ungefähr 0,016. Die Fallgeschwindigkeit bleibt so gleich, auch wenn ein
Bild mal länger dauert. Wir deckeln dt bei 0,05, damit ein kurzer Hänger
die Spitzhacke nicht durch die Blöcke wirft.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from dataclasses import replace
from pathlib import Path

# Kein Ton im Spiel. Ohne diese Zeile meckert SDL auf Rechnern ohne Soundkarte
# und kann den Start stören. Wer einen Treiber setzen will, tut das davor.
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from cave_dig.chat import create_provider
from cave_dig.config import (
    DAILY_QUOTA_LIMIT,
    ConfigError,
    estimate_daily_chat_units,
    load_config,
)
from cave_dig.fonts import FontBook
from cave_dig.game import Game
from cave_dig.languages import LanguageError, load_languages
from cave_dig.logging_setup import setup_logging
from cave_dig.paths import project_path
from cave_dig.render import Renderer, present
from cave_dig.textures import TextureAtlas

log = logging.getLogger("cave_dig.app")

# start.bat und start.sh starten das Spiel nach einem Absturz neu.
# Bei diesem Code nicht: eine falsche Konfiguration heilt kein Neustart.
EXIT_BAD_CONFIG = 3


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.headless:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ["SDL_AUDIODRIVER"] = "dummy"
    try:
        config = load_config(args.config)
        languages = load_languages(config.languages_file)
    except (ConfigError, LanguageError) as exc:
        print(exc)
        return EXIT_BAD_CONFIG

    setup_logging(config.log_dir)
    if args.provider:
        config = replace(config, provider=args.provider)
    if config.provider == "youtube":
        units = estimate_daily_chat_units(config.youtube_min_poll_seconds)
        log.info(
            "YouTube-Abfrage alle %.0f s, grob %s Einheiten pro Tag (Limit %s).",
            config.youtube_min_poll_seconds,
            f"{units:,}".replace(",", "."),
            f"{DAILY_QUOTA_LIMIT:,}".replace(",", "."),
        )
        if units > 9_500:
            log.warning(
                "Das Intervall ist für 24/7 zu kurz und kann das Tageslimit sprengen. "
                "min_poll_seconds auf 50 oder höher setzen."
            )

    pygame.init()
    pygame.display.set_caption(config.title)
    try:
        window = pygame.display.set_mode((config.window_width, config.window_height))
    except pygame.error as exc:
        log.error("Fenster konnte nicht geöffnet werden: %s", exc)
        print("Fenster konnte nicht geöffnet werden.", exc)
        return 2

    logical = pygame.Surface((config.logical_width, config.logical_height))
    fonts = FontBook(project_path("assets", "fonts"))
    textures = TextureAtlas(config.blocks, config.block_size, project_path("assets", "textures"))
    if textures.pickaxe is not None:
        pygame.display.set_icon(textures.pickaxe)
    renderer = Renderer(config, fonts, textures)
    seed = args.seed if args.seed is not None else None
    game = Game(config, languages, seed=seed, demo=args.demo)
    provider = create_provider(config, languages, seed=args.seed or 1, demo=args.demo)
    provider.start()
    game.status_line = provider.status

    clock = pygame.time.Clock()
    fast = args.frames > 0
    shot_frames = set(args.screenshot_frames)
    shot_dir = args.screenshot_dir
    if shot_dir is not None:
        shot_dir.mkdir(parents=True, exist_ok=True)
    frame = 0
    running = True
    fps_samples: list[float] = []

    def request_stop(signum: int, _frame: object) -> None:
        nonlocal running
        log.info("Signal %s, Spiel wird beendet und gespeichert.", signum)
        running = False

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)

    log.info(
        "Start. Anbieter %s, Fenster %sx%s, innen %sx%s.",
        config.provider,
        config.window_width,
        config.window_height,
        config.logical_width,
        config.logical_height,
    )
    try:
        while running:
            if fast and frame >= args.frames:
                break
            if fast:
                dt = 1.0 / config.fps
            else:
                dt = clock.tick(config.fps) / 1000.0
                if dt <= 0:
                    dt = 1.0 / config.fps
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    _on_key(event.key, game, window, logical)
            game.local_direction = _held_direction()
            try:
                game.status_line = provider.status
                game.handle_messages(provider.poll(game.time))
                game.update(dt)
                renderer.draw(logical, game)
                present(window, logical, config.colors["background_deep"])
                pygame.display.flip()
            except Exception:
                log.exception("Fehler im Bild, das Spiel läuft weiter.")
            frame += 1
            if shot_dir is not None and frame in shot_frames:
                path = shot_dir / f"cave-dig-{frame:04d}.png"
                pygame.image.save(window, path)
                log.info("Bild gespeichert: %s", path)
            if not fast:
                fps_samples.append(clock.get_fps())
                if len(fps_samples) >= config.fps * 30:
                    average = sum(fps_samples) / len(fps_samples)
                    if average < config.fps - 5:
                        log.warning("Bildrate im Schnitt %.1f, Ziel %s.", average, config.fps)
                    fps_samples.clear()
    except Exception:
        # Sonst stünde der Grund nur in der Konsole und nicht in der Logdatei.
        log.exception("Spiel abgestürzt.")
        raise
    finally:
        provider.stop()
        game.save()
        pygame.quit()
    return 0


def _on_key(key: int, game: Game, window: pygame.Surface, logical: pygame.Surface) -> None:
    if key in (pygame.K_LEFT, pygame.K_a):
        game.handle_local_vote("left")
    elif key in (pygame.K_RIGHT, pygame.K_d):
        game.handle_local_vote("right")
    elif key == pygame.K_SPACE:
        game.start_event(None)
    elif key == pygame.K_ESCAPE:
        pygame.event.post(pygame.event.Event(pygame.QUIT))
    elif key == pygame.K_F12:
        folder = project_path("screenshots")
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "cave-dig-f12.png"
        present(window, logical, game.config.colors["background_deep"])
        pygame.image.save(window, path)
        log.info("Bild gespeichert: %s", path)


def _held_direction() -> int:
    keys = pygame.key.get_pressed()
    direction = 0
    if keys[pygame.K_LEFT] or keys[pygame.K_a]:
        direction -= 1
    if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
        direction += 1
    return direction


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cave Dig starten.")
    parser.add_argument("--config", type=_path, default=None, help="Andere config.yaml")
    parser.add_argument("--provider", choices=("simulator", "youtube", "twitch"))
    parser.add_argument("--seed", type=int, default=None, help="Feste Höhle, 0 bleibt Zufall")
    parser.add_argument("--demo", action="store_true", help="Schnellere Bots, eine Erzader")
    parser.add_argument("--headless", action="store_true", help="Kein echtes Fenster (Tests)")
    parser.add_argument("--frames", type=int, default=0, help="Nach N Bildern beenden")
    parser.add_argument("--screenshot-dir", type=_path, default=None)
    parser.add_argument(
        "--screenshot-frames",
        type=_frame_list,
        default=[],
        help="Bildnummern, zum Beispiel 45,150,230",
    )
    return parser.parse_args(argv)


def _path(value: str) -> Path:
    return Path(value)


def _frame_list(value: str) -> list[int]:
    if not value.strip():
        return []
    return [int(part) for part in value.split(",") if part.strip()]


if __name__ == "__main__":
    sys.exit(main())
