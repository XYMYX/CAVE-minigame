"""Baut die Chat-Anbieter, die in der Konfiguration stehen.

Ein neuer Anbieter braucht drei Dinge: eine Klasse mit start, poll und stop,
einen Eintrag in _FACTORIES und seinen Namen in config.PROVIDER_NAMES.
Mehrere Anbieter gleichzeitig funktionieren dann von selbst.
"""

from __future__ import annotations

from typing import Callable

from cave_dig.chat.base import ChatProvider
from cave_dig.chat.multi import MultiChatProvider
from cave_dig.chat.simulator import SimulatorProvider
from cave_dig.chat.twitch import TwitchChatProvider
from cave_dig.chat.youtube import YouTubeChatProvider
from cave_dig.config import PROVIDER_NAMES, ConfigError, GameConfig
from cave_dig.languages import LanguageTable

_Factory = Callable[[GameConfig, LanguageTable, int, bool], ChatProvider]

_FACTORIES: dict[str, _Factory] = {
    "simulator": lambda config, languages, seed, demo: SimulatorProvider(
        config, languages, seed=seed, demo=demo
    ),
    "youtube": lambda config, languages, seed, demo: YouTubeChatProvider(config),
    "twitch": lambda config, languages, seed, demo: TwitchChatProvider(config),
}


def create_provider(
    config: GameConfig,
    languages: LanguageTable,
    *,
    seed: int,
    demo: bool,
) -> ChatProvider:
    providers = [_build(kind, config, languages, seed, demo) for kind in config.providers]
    # Ein einzelner Anbieter läuft direkt, ohne Hülle.
    return providers[0] if len(providers) == 1 else MultiChatProvider(providers)


def _build(
    kind: str, config: GameConfig, languages: LanguageTable, seed: int, demo: bool
) -> ChatProvider:
    factory = _FACTORIES.get(kind)
    if factory is None:
        allowed = ", ".join(PROVIDER_NAMES)
        raise ConfigError(f"chat.provider '{kind}' kenne ich nicht. Erlaubt: {allowed}.")
    return factory(config, languages, seed, demo)
