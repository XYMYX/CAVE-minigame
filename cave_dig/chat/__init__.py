"""Baut den Chat-Anbieter, der in der Konfiguration steht."""

from __future__ import annotations

from cave_dig.chat.base import ChatProvider
from cave_dig.chat.simulator import SimulatorProvider
from cave_dig.chat.twitch import TwitchChatProvider
from cave_dig.chat.youtube import YouTubeChatProvider
from cave_dig.config import ConfigError, GameConfig
from cave_dig.languages import LanguageTable


def create_provider(
    config: GameConfig,
    languages: LanguageTable,
    *,
    seed: int,
    demo: bool,
) -> ChatProvider:
    kind = config.provider
    if kind == "simulator":
        return SimulatorProvider(config, languages, seed=seed, demo=demo)
    if kind == "youtube":
        return YouTubeChatProvider(config)
    if kind == "twitch":
        return TwitchChatProvider(config)
    raise ConfigError(
        f"chat.provider '{kind}' kenne ich nicht. Erlaubt: simulator, youtube, twitch."
    )
