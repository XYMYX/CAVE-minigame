"""Platzhalter für Twitch. Gleiche Schnittstelle, noch ohne Verbindung.

Wenn du Twitch später anschließt, bleibt der Rest des Spiels gleich.
poll() liefert dann ChatMessage-Objekte, so wie der YouTube-Anbieter.

Ein üblicher Weg ohne extra Bibliothek ist der IRC-Anschluss von Twitch:

  1. Verbinden mit irc.chat.twitch.tv, Port 6697 (TLS).
  2. Senden:  PASS oauth:DEIN_TOKEN
              NICK dein_botname
              JOIN #dein_kanal
  3. Zeilen lesen. Eine Chatzeile sieht so aus:
              :name!name@name.tmi.twitch.tv PRIVMSG #kanal :links
  4. Den Text hinter dem zweiten Doppelpunkt als ChatMessage in eine
     Warteschlange legen. poll() leert diese Warteschlange.
  5. Bei Verbindungsabbruch warten und neu verbinden. Nie die Ausnahme
     aus dem Thread ins Spiel reichen.

Bis das eingebaut ist, läuft das Spiel weiter und zeigt den Hinweis unten.
"""

from __future__ import annotations

import logging

from cave_dig.chat.base import ChatMessage, ChatProvider
from cave_dig.config import GameConfig
from cave_dig.i18n import load_catalog

log = logging.getLogger("cave_dig.twitch")


class TwitchChatProvider(ChatProvider):
    def __init__(self, config: GameConfig) -> None:
        super().__init__()
        self.channel = config.twitch_channel
        self._status = load_catalog(config.language, config.locales_dir).t("status.twitch")

    def start(self) -> None:
        if self.channel:
            log.warning(
                "Twitch-Kanal '%s' ist eingetragen, der Anbieter verbindet aber noch nicht.",
                self.channel,
            )
        else:
            log.warning("Twitch-Anbieter ist ein Platzhalter. Kein Chat wird gelesen.")

    def poll(self, now: float) -> list[ChatMessage]:
        return []

    def stop(self) -> None:
        return None
