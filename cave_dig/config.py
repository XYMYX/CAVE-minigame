"""Lädt config.yaml, füllt Lücken mit Standardwerten und liest .env.

Wenn ein Schlüssel fehlt, nimmt das Spiel den Wert aus DEFAULTS. So kann
eine alte config.yaml weiterlaufen, nachdem eine neue Option dazugekommen
ist. Ein komplett falsches YAML stoppt den Start mit einer deutschen
Meldung, statt mitten in der Nacht abzustürzen.
"""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

from cave_dig.blockdefs import PATTERNS
from cave_dig.paths import project_path

DAILY_QUOTA_LIMIT = 10_000
LIVE_CHAT_UNITS = 5


class ConfigError(Exception):
    """Die Konfiguration ist da, aber so nicht benutzbar."""


@dataclass(frozen=True)
class BlockType:
    id: str
    name: str
    hits: int
    points: int
    color: tuple[int, int, int]
    accent: tuple[int, int, int]
    pattern: str
    unbreakable: bool = False
    explosive: bool = False
    solid: bool = True


@dataclass(frozen=True)
class Band:
    until_row: int
    fill: dict[str, int]
    vein_chance: float
    veins: dict[str, int]


@dataclass(frozen=True)
class GameConfig:
    title: str
    logical_width: int
    logical_height: int
    window_width: int
    window_height: int
    fps: int
    columns: int
    wall_columns: int
    sky_rows: int
    shelf_every: int
    shelf_gap: int
    vote_window_seconds: float
    one_vote_per_user: bool
    provider: str
    languages_file: Path
    save_path: Path
    log_dir: Path
    language: str
    locales_dir: Path
    blocks: dict[str, BlockType]
    bands: tuple[Band, ...]
    colors: dict[str, tuple[int, int, int]]
    gravity: float
    max_fall: float
    restitution: float
    horizontal_drag: float
    nudge_speed: float
    steer_force: float
    hold_seconds: float
    max_horizontal_speed: float
    hit_cooldown: float
    pickaxe_radius: float
    local_steer: float
    local_voter_name: str
    integrity_max: float
    passive_drain: float
    regen_per_second: float
    regen_min_speed: float
    chip_damage: float
    bedrock_damage: float
    explosion_damage: float
    explosion_radius: float
    cave_in_damage: float
    stuck_seconds: float
    depth_bonus_per_meter: float
    depth_bonus_cap: float
    round_end_pause: float
    events_enabled: bool
    event_cooldown: float
    event_user_cooldown: float
    event_command: str
    random_min_seconds: float
    random_max_seconds: float
    random_chance: float
    event_aliases: dict[str, str]
    event_durations: dict[str, float]
    event_ids: tuple[str, ...]
    hint_seconds: float
    show_status: bool
    bot_enabled: bool
    bot_interval_min: float
    bot_interval_max: float
    bot_bias_left: float
    youtube_mode: str
    youtube_transport: str
    youtube_api_key: str
    youtube_video_id: str
    youtube_min_poll_seconds: float
    youtube_client_secrets: Path
    youtube_token_path: Path
    twitch_channel: str
    chat_blocked: tuple[str, ...]
    world_seed: int

    @property
    def steer_hold(self) -> float:
        """Wie lange der Schub wirkt. YouTube liefert nur alle min_poll_seconds Stimmen."""
        if self.provider == "youtube" and self.youtube_transport == "poll":
            return max(self.hold_seconds, self.youtube_min_poll_seconds)
        return self.hold_seconds

    @property
    def block_size(self) -> int:
        """Pixel pro Block auf der inneren Zeichenfläche. Geht immer auf die Breite."""
        return max(8, self.logical_width // self.columns)


# Standardwerte. config.yaml darf einzelne Schlüssel weglassen.
DEFAULTS: dict = {
    "game": {
        "title": "Cave Dig",
        "logical_width": 540,
        "logical_height": 960,
        "window_width": 1080,
        "window_height": 1920,
        "fps": 60,
        "columns": 12,
        "wall_columns": 1,
        "sky_rows": 4,
        "shelf_every": 16,
        "shelf_gap": 3,
        "world_seed": 0,
        "hint_seconds": 3.2,
        "show_status": True,
        "round_end_pause": 4.0,
        "languages_file": "languages.yaml",
        "save_path": "data/stand.json",
        "log_dir": "logs",
        # en = locales/en.yaml. de liegt daneben. Weitere Dateien ebenso.
        "language": "en",
        "locales_dir": "locales",
    },
    "vote": {
        "window_seconds": 2.5,
        "one_per_user": True,
        "nudge_speed": 280,
        "steer_force": 460,
        "hold_seconds": 5,
        "local_steer": 460,
        "local_voter_name": "Local",
    },
    "physics": {
        "gravity": 860,
        "max_fall": 380,
        "restitution": 0.42,
        "horizontal_drag": 1.15,
        "max_horizontal_speed": 460,
        "hit_cooldown": 0.18,
        "pickaxe_radius": 11,
    },
    "integrity": {
        "maximum": 100,
        "passive_drain": 0.1,
        "regen_per_second": 2.4,
        "regen_min_speed": 90,
        "chip_damage": 0.05,
        "bedrock_damage": 0.1,
        "explosion_damage": 26,
        "explosion_radius": 2.15,
        "cave_in_damage": 12,
        "stuck_seconds": 110,
    },
    "score": {
        "depth_bonus_per_meter": 0.002,
        "depth_bonus_cap": 3.0,
    },
    "events": {
        "enabled": True,
        "cooldown_seconds": 40,
        "user_cooldown_seconds": 300,
        "command": "!event",
        "random_min_seconds": 55,
        "random_max_seconds": 95,
        "random_chance": 0.7,
        "ids": ["cave_in", "darkness", "explosion", "ore_vein"],
        "durations": {
            "cave_in": 5.0,
            "darkness": 8.0,
            "explosion": 3.5,
            "ore_vein": 4.5,
        },
        "aliases": {
            "cavein": "cave_in",
            "cave_in": "cave_in",
            "einsturz": "cave_in",
            "darkness": "darkness",
            "dunkel": "darkness",
            "dunkelheit": "darkness",
            "explosion": "explosion",
            "sprengung": "explosion",
            "vein": "ore_vein",
            "ader": "ore_vein",
            "erzader": "ore_vein",
            "erz": "ore_vein",
        },
    },
    "colors": {
        "background_top": [24, 18, 26],
        "background_deep": [6, 8, 12],
        "text": [236, 228, 210],
        "muted": [176, 164, 146],
        "left": [232, 164, 70],
        "right": [72, 198, 188],
        "accent": [214, 176, 96],
        "danger": [214, 86, 64],
        "good": [118, 198, 124],
    },
    "chat": {
        "provider": "simulator",
        "blocked": [],
        "simulator": {
            "bot_enabled": True,
            "bot_interval_min": 0.28,
            "bot_interval_max": 0.8,
            "bot_bias_left": 0.5,
        },
        "youtube": {
            "mode": "api_key",
            "transport": "stream",
            "api_key": "",
            "video_id": "",
            "min_poll_seconds": 50,
            "client_secrets": "client_secret.json",
            "token_path": "tokens/youtube_token.json",
        },
        "twitch": {
            "channel": "",
        },
    },
    "blocks": {
        "dirt": {
            "name": "Erde",
            "hits": 1,
            "points": 10,
            "color": [142, 92, 52],
            "accent": [88, 56, 32],
            "pattern": "speckles",
        },
        "gravel": {
            "name": "Kies",
            "hits": 1,
            "points": 14,
            "color": [122, 116, 106],
            "accent": [170, 162, 148],
            "pattern": "pebbles",
        },
        "stone": {
            "name": "Stein",
            "hits": 2,
            "points": 22,
            "color": [74, 96, 108],
            "accent": [46, 60, 70],
            "pattern": "cracks",
        },
        "coal": {
            "name": "Kohle",
            "hits": 2,
            "points": 55,
            "color": [62, 66, 70],
            "accent": [16, 16, 18],
            "pattern": "ore",
        },
        "iron": {
            "name": "Eisen",
            "hits": 3,
            "points": 130,
            "color": [104, 92, 74],
            "accent": [196, 102, 54],
            "pattern": "ore",
        },
        "gold": {
            "name": "Gold",
            "hits": 3,
            "points": 280,
            "color": [108, 90, 58],
            "accent": [228, 184, 72],
            "pattern": "ore",
        },
        "gem": {
            "name": "Kristall",
            "hits": 4,
            "points": 800,
            "color": [22, 78, 84],
            "accent": [64, 224, 198],
            "pattern": "crystals",
        },
        "charge": {
            "name": "Sprengsatz",
            "hits": 1,
            "points": 40,
            "color": [48, 40, 36],
            "accent": [226, 112, 46],
            "pattern": "charge",
            "explosive": True,
        },
        "bedrock": {
            "name": "Urgestein",
            "hits": 1,
            "points": 0,
            "color": [24, 20, 32],
            "accent": [104, 70, 128],
            "pattern": "veins",
            "unbreakable": True,
        },
    },
    "generation": {
        "bands": [
            {
                "until_row": 36,
                "vein_chance": 0.18,
                "fill": {"dirt": 38, "gravel": 18, "stone": 32, "coal": 7, "air": 5},
                "veins": {"coal": 75, "iron": 25},
            },
            {
                "until_row": 90,
                "vein_chance": 0.26,
                "fill": {
                    "dirt": 8,
                    "gravel": 10,
                    "stone": 52,
                    "coal": 10,
                    "iron": 8,
                    "air": 8,
                    "charge": 4,
                },
                "veins": {"coal": 20, "iron": 55, "gold": 25},
            },
            {
                "until_row": 180,
                "vein_chance": 0.3,
                "fill": {
                    "stone": 58,
                    "gravel": 6,
                    "iron": 8,
                    "gold": 6,
                    "coal": 4,
                    "air": 12,
                    "charge": 6,
                },
                "veins": {"iron": 25, "gold": 40, "gem": 35},
            },
            {
                "until_row": 1000000000,
                "vein_chance": 0.34,
                "fill": {
                    "stone": 50,
                    "gold": 8,
                    "gem": 8,
                    "air": 14,
                    "charge": 8,
                    "gravel": 6,
                    "bedrock": 6,
                },
                "veins": {"gold": 30, "gem": 70},
            },
        ]
    },
}


def load_config(path: Path | None = None) -> GameConfig:
    """Liest die Nutzer-Datei, mischt Standardwerte darunter und wendet .env an."""
    file_path = path or project_path("config.yaml")
    load_dotenv(project_path(".env"))
    user: dict = {}
    if file_path.exists():
        try:
            loaded = yaml.safe_load(file_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ConfigError(f"Konfiguration nicht lesbar: {file_path}") from exc
        except yaml.YAMLError as exc:
            raise ConfigError(
                f"config.yaml ist kein gültiges YAML.\n{exc}\n"
                "Tipp: Einrückung mit Leerzeichen, nicht mit Tab."
            ) from exc
        if loaded is None:
            loaded = {}
        if not isinstance(loaded, dict):
            raise ConfigError("config.yaml muss aus Schlüsseln wie game: und blocks: bestehen.")
        user = loaded
    elif path is not None:
        raise ConfigError(f"Konfigurationsdatei fehlt: {file_path}")

    data = _deep_merge(DEFAULTS, user)
    try:
        if str(data["chat"]["youtube"].get("api_key") or "").strip():
            # Den Wert nicht ausgeben, er soll in keinem Log landen.
            raise ConfigError(
                "chat.youtube.api_key steht in config.yaml, und diese Datei liegt in Git. "
                "Bitte dort löschen und als YOUTUBE_API_KEY in .env eintragen."
            )
        _apply_env(data)
        return _build(data)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        # Zum Beispiel "game:" ohne Inhalt oder "hits: abc".
        raise ConfigError(
            "config.yaml passt nicht: Ein Abschnitt ist leer oder ein Wert hat "
            f"den falschen Typ.\nDetails: {exc}"
        ) from exc


def simulator_save_path(path: Path) -> Path:
    """stand.json wird zu stand.simulator.json. Bots gehören nicht in die echte Liste."""
    return path.with_name(f"{path.stem}.simulator{path.suffix}")


def estimate_daily_chat_units(poll_seconds: float, cost_per_call: int = LIVE_CHAT_UNITS) -> int:
    """Grobe Rechnung: Aufrufe pro Tag mal Kosten pro Aufruf.

    86.400 Sekunden hat ein Tag. Bei 50 Sekunden Abstand sind das 1.728
    Aufrufe. liveChatMessages.list kostet 5 Einheiten, also 8.640.
    Das Tageslimit der YouTube Data API liegt normalerweise bei 10.000.
    """
    if poll_seconds <= 0:
        raise ConfigError("min_poll_seconds muss größer als 0 sein.")
    calls = int(86400 // poll_seconds)
    return calls * cost_per_call


def _apply_env(data: dict) -> None:
    youtube = data["chat"]["youtube"]
    if os.getenv("YOUTUBE_API_KEY"):
        youtube["api_key"] = os.environ["YOUTUBE_API_KEY"].strip()
    if os.getenv("YOUTUBE_VIDEO_ID"):
        youtube["video_id"] = os.environ["YOUTUBE_VIDEO_ID"].strip()
    if os.getenv("YOUTUBE_CLIENT_SECRETS"):
        youtube["client_secrets"] = os.environ["YOUTUBE_CLIENT_SECRETS"].strip()
    mode = os.getenv("YOUTUBE_MODE")
    if mode:
        youtube["mode"] = mode.strip()
    provider = os.getenv("CAVE_DIG_PROVIDER")
    if provider:
        data["chat"]["provider"] = provider.strip()


def _build(data: dict) -> GameConfig:
    game = data["game"]
    vote = data["vote"]
    physics = data["physics"]
    integrity = data["integrity"]
    score = data["score"]
    events = data["events"]
    chat = data["chat"]
    youtube = chat["youtube"]
    simulator = chat["simulator"]

    logical_w = _int(game, "logical_width", 200, 1440)
    logical_h = _int(game, "logical_height", 320, 2560)
    columns = _int(game, "columns", 6, 24)
    if logical_w // columns < 8:
        raise ConfigError("Zu viele Spalten für die Breite. columns kleiner machen.")

    provider = str(chat.get("provider", "simulator")).strip().lower()
    if provider not in ("simulator", "youtube", "twitch"):
        raise ConfigError(
            f"chat.provider '{provider}' kenne ich nicht. "
            "Erlaubt: simulator, youtube, twitch."
        )

    mode = str(youtube.get("mode", "api_key")).strip().lower()
    if mode not in ("api_key", "oauth"):
        raise ConfigError("chat.youtube.mode muss api_key oder oauth sein.")

    transport = str(youtube.get("transport", "stream")).strip().lower()
    if transport not in ("stream", "poll"):
        raise ConfigError("chat.youtube.transport muss stream oder poll sein.")

    blocks = _build_blocks(data.get("blocks") or {})
    bands = _build_bands(data.get("generation") or {}, blocks)
    colors = {
        key: _color(value, f"colors.{key}")
        for key, value in (data.get("colors") or {}).items()
    }
    aliases = {
        str(key).casefold(): str(value)
        for key, value in (events.get("aliases") or {}).items()
    }
    durations = {
        str(key): _float_value(value, f"events.durations.{key}", 0.2, 120)
        for key, value in (events.get("durations") or {}).items()
    }
    event_ids = tuple(str(item) for item in (events.get("ids") or []))
    for event_id in event_ids:
        if event_id not in durations:
            durations[event_id] = 5.0

    poll = _float_value(youtube.get("min_poll_seconds"), "min_poll_seconds", 1, 3600)
    return GameConfig(
        title=str(game.get("title") or "Cave Dig"),
        logical_width=logical_w,
        logical_height=logical_h,
        window_width=_int(game, "window_width", 200, 2160),
        window_height=_int(game, "window_height", 320, 3840),
        fps=_int(game, "fps", 30, 120),
        columns=columns,
        wall_columns=_int(game, "wall_columns", 1, 3),
        sky_rows=_int(game, "sky_rows", 1, 12),
        shelf_every=_int(game, "shelf_every", 6, 80),
        shelf_gap=_int(game, "shelf_gap", 1, 8),
        vote_window_seconds=_float_value(vote.get("window_seconds"), "vote.window_seconds", 0.4, 30),
        one_vote_per_user=bool(vote.get("one_per_user", True)),
        provider=provider,
        languages_file=_resolve(str(game.get("languages_file", "languages.yaml"))),
        save_path=_resolve(str(game.get("save_path", "data/stand.json"))),
        log_dir=_resolve(str(game.get("log_dir", "logs"))),
        language=_language_code(game.get("language")),
        locales_dir=_resolve(str(game.get("locales_dir") or "locales")),
        blocks=blocks,
        bands=bands,
        colors=colors,
        gravity=_float_value(physics.get("gravity"), "gravity", 50, 4000),
        max_fall=_float_value(physics.get("max_fall"), "max_fall", 40, 2000),
        restitution=_float_value(physics.get("restitution"), "restitution", 0, 1),
        horizontal_drag=_float_value(physics.get("horizontal_drag"), "horizontal_drag", 0, 10),
        nudge_speed=_float_value(vote.get("nudge_speed"), "nudge_speed", 0, 2000),
        steer_force=_float_value(vote.get("steer_force"), "steer_force", 0, 4000),
        hold_seconds=_float_value(vote.get("hold_seconds"), "hold_seconds", 0, 600),
        max_horizontal_speed=_float_value(
            physics.get("max_horizontal_speed"), "max_horizontal_speed", 40, 2000
        ),
        hit_cooldown=_float_value(physics.get("hit_cooldown"), "hit_cooldown", 0.02, 2),
        pickaxe_radius=_float_value(physics.get("pickaxe_radius"), "pickaxe_radius", 4, 40),
        local_steer=_float_value(vote.get("local_steer"), "local_steer", 0, 4000),
        local_voter_name=str(vote.get("local_voter_name") or "Local")[:24],
        integrity_max=_float_value(integrity.get("maximum"), "integrity.maximum", 10, 10000),
        passive_drain=_float_value(integrity.get("passive_drain"), "passive_drain", 0, 50),
        regen_per_second=_float_value(integrity.get("regen_per_second"), "regen", 0, 100),
        regen_min_speed=_float_value(integrity.get("regen_min_speed"), "regen_min_speed", 0, 2000),
        chip_damage=_float_value(integrity.get("chip_damage"), "chip_damage", 0, 50),
        bedrock_damage=_float_value(integrity.get("bedrock_damage"), "bedrock_damage", 0, 100),
        explosion_damage=_float_value(integrity.get("explosion_damage"), "explosion_damage", 0, 200),
        explosion_radius=_float_value(integrity.get("explosion_radius"), "explosion_radius", 0.5, 6),
        cave_in_damage=_float_value(integrity.get("cave_in_damage"), "cave_in_damage", 0, 100),
        stuck_seconds=_float_value(integrity.get("stuck_seconds"), "stuck_seconds", 3, 120),
        depth_bonus_per_meter=_float_value(
            score.get("depth_bonus_per_meter"), "depth_bonus_per_meter", 0, 1
        ),
        depth_bonus_cap=_float_value(score.get("depth_bonus_cap"), "depth_bonus_cap", 1, 20),
        round_end_pause=_float_value(game.get("round_end_pause"), "round_end_pause", 0.5, 30),
        events_enabled=bool(events.get("enabled", True)),
        event_cooldown=_float_value(events.get("cooldown_seconds"), "cooldown", 1, 3600),
        event_user_cooldown=_float_value(
            events.get("user_cooldown_seconds"), "user_cooldown_seconds", 0, 86400
        ),
        event_command=str(events.get("command") or "!event"),
        random_min_seconds=_float_value(events.get("random_min_seconds"), "random_min", 5, 3600),
        random_max_seconds=_float_value(events.get("random_max_seconds"), "random_max", 5, 7200),
        random_chance=_float_value(events.get("random_chance"), "random_chance", 0, 1),
        event_aliases=aliases,
        event_durations=durations,
        event_ids=event_ids,
        hint_seconds=_float_value(game.get("hint_seconds"), "hint_seconds", 0.5, 30),
        show_status=bool(game.get("show_status", True)),
        bot_enabled=bool(simulator.get("bot_enabled", True)),
        bot_interval_min=_float_value(simulator.get("bot_interval_min"), "bot_interval_min", 0.05, 30),
        bot_interval_max=_float_value(simulator.get("bot_interval_max"), "bot_interval_max", 0.05, 60),
        bot_bias_left=_float_value(simulator.get("bot_bias_left"), "bot_bias_left", 0, 1),
        youtube_mode=mode,
        youtube_transport=transport,
        youtube_api_key=str(youtube.get("api_key") or "").strip(),
        youtube_video_id=str(youtube.get("video_id") or "").strip(),
        youtube_min_poll_seconds=poll,
        youtube_client_secrets=_resolve(str(youtube.get("client_secrets") or "client_secret.json")),
        youtube_token_path=_resolve(str(youtube.get("token_path") or "tokens/youtube_token.json")),
        twitch_channel=str((chat.get("twitch") or {}).get("channel") or "").strip().lstrip("#"),
        chat_blocked=_blocked(chat.get("blocked")),
        world_seed=_int(game, "world_seed", 0, 2_000_000_000),
    )


def _build_blocks(raw: dict) -> dict[str, BlockType]:
    blocks: dict[str, BlockType] = {}
    for block_id, body in raw.items():
        if not isinstance(body, dict):
            raise ConfigError(f"Block '{block_id}' muss Werte wie hits und points enthalten.")
        pattern = str(body.get("pattern", "speckles"))
        if pattern not in PATTERNS:
            raise ConfigError(
                f"Block '{block_id}' hat das Muster '{pattern}'. "
                f"Erlaubt: {', '.join(sorted(PATTERNS))}."
            )
        blocks[str(block_id)] = BlockType(
            id=str(block_id),
            name=str(body.get("name") or block_id),
            hits=max(1, int(body.get("hits", 1))),
            points=max(0, int(body.get("points", 0))),
            color=_color(body.get("color"), f"{block_id}.color"),
            accent=_color(body.get("accent") or body.get("color"), f"{block_id}.accent"),
            pattern=pattern,
            unbreakable=bool(body.get("unbreakable", False)),
            explosive=bool(body.get("explosive", False)),
            solid=True,
        )
    if "bedrock" not in blocks:
        raise ConfigError("In blocks fehlt 'bedrock'. Die Wände brauchen diesen Typ.")
    # Luft ist kein YAML-Eintrag, damit die Liste der echten Blöcke übersichtlich bleibt.
    blocks["air"] = BlockType(
        id="air",
        name="Luft",
        hits=1,
        points=0,
        color=(0, 0, 0),
        accent=(0, 0, 0),
        pattern="none",
        solid=False,
    )
    return blocks


def _build_bands(generation: dict, blocks: dict[str, BlockType]) -> tuple[Band, ...]:
    raw_bands = generation.get("bands") or []
    if not isinstance(raw_bands, list) or not raw_bands:
        raise ConfigError("generation.bands braucht mindestens ein Tiefenband.")
    bands: list[Band] = []
    for index, body in enumerate(raw_bands):
        if not isinstance(body, dict):
            raise ConfigError(f"Band {index} ist kein YAML-Block.")
        fill = _weights(body.get("fill"), f"Band {index} fill", blocks)
        veins = _weights(body.get("veins"), f"Band {index} veins", blocks)
        bands.append(
            Band(
                until_row=int(body.get("until_row", 10**9)),
                fill=fill,
                vein_chance=float(body.get("vein_chance", 0)),
                veins=veins,
            )
        )
    return tuple(bands)


def _weights(raw: object, label: str, blocks: dict[str, BlockType]) -> dict[str, int]:
    if not isinstance(raw, dict) or not raw:
        raise ConfigError(f"{label} braucht Gewichte, zum Beispiel stone: 10.")
    weights: dict[str, int] = {}
    for key, value in raw.items():
        name = str(key)
        if name not in blocks:
            raise ConfigError(
                f"{label}: Block '{name}' gibt es nicht. Lege ihn unter blocks an "
                "oder korrigiere den Namen."
            )
        amount = int(value)
        if amount < 0:
            raise ConfigError(f"{label}: Gewicht von '{name}' darf nicht negativ sein.")
        if amount > 0:
            weights[name] = amount
    if not weights:
        raise ConfigError(f"{label} hat nur Nullen.")
    return weights


def _color(value: object, label: str) -> tuple[int, int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ConfigError(f"Farbe {label} braucht drei Zahlen, zum Beispiel [220, 180, 90].")
    channels: list[int] = []
    for channel in value:
        if isinstance(channel, bool) or not isinstance(channel, int) or not 0 <= channel <= 255:
            raise ConfigError(f"Farbe {label}: jede Zahl muss zwischen 0 und 255 liegen.")
        channels.append(channel)
    return channels[0], channels[1], channels[2]


def _int(section: dict, key: str, low: int, high: int) -> int:
    value = section.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{key} muss eine ganze Zahl sein.")
    if not low <= value <= high:
        raise ConfigError(f"{key} muss zwischen {low} und {high} liegen, ist aber {value}.")
    return value


def _float_value(value: object, label: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{label} muss eine Zahl sein.")
    number = float(value)
    if not low <= number <= high:
        raise ConfigError(f"{label} muss zwischen {low} und {high} liegen, ist aber {number}.")
    return number


def _blocked(value: object) -> tuple[str, ...]:
    """Liste aus chat.blocked, klein geschrieben. Leere Einträge fallen weg."""
    if value is None:
        return ()
    # Ein einzelner Text würde sonst Buchstabe für Buchstabe sperren.
    if not isinstance(value, list):
        raise ConfigError("chat.blocked muss eine Liste sein, zum Beispiel [Name1, Name2].")
    entries = (str(item).strip().casefold() for item in value)
    return tuple(entry for entry in entries if entry)


def _language_code(value: object) -> str:
    """Kurzer Dateiname ohne Pfad. 'English!' wird zu en, damit nichts schief läuft."""
    text = str(value or "en").strip().lower()
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-_")
    if not text or len(text) > 16 or any(char not in allowed for char in text):
        return "en"
    return text


def _resolve(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return project_path(value)


def _deep_merge(base: dict, override: dict) -> dict:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged
