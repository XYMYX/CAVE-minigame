"""Mehrere Chat-Quellen, die für das Spiel wie eine einzige aussehen.

Jede Quelle ist für sich abgesichert: Wirft eine davon einen Fehler, läuft
die andere weiter und das Spiel merkt nichts davon.
"""

from __future__ import annotations

import logging

from cave_dig.chat.base import ChatMessage, ChatProvider

log = logging.getLogger("cave_dig.chat")


class MultiChatProvider(ChatProvider):
    def __init__(self, providers: list[ChatProvider]) -> None:
        super().__init__()
        self.providers = list(providers)
        # Damit ein Dauerfehler in poll() nicht jedes Bild das Log füllt.
        self._failing: set[int] = set()

    @property
    def status(self) -> str:
        """Eine Zeile pro Quelle. render.py zeichnet sie untereinander."""
        lines = [provider.status for provider in self.providers if provider.status]
        return "\n".join(dict.fromkeys(lines))

    def start(self) -> None:
        running: list[ChatProvider] = []
        for provider in self.providers:
            try:
                provider.start()
            except Exception:
                log.exception("Chat-Quelle %s startet nicht.", type(provider).__name__)
            else:
                running.append(provider)
        self.providers = running

    def poll(self, now: float) -> list[ChatMessage]:
        messages: list[ChatMessage] = []
        for index, provider in enumerate(self.providers):
            try:
                messages.extend(provider.poll(now))
            except Exception:
                if index not in self._failing:
                    self._failing.add(index)
                    log.exception("Chat-Quelle %s liefert nicht.", type(provider).__name__)
            else:
                self._failing.discard(index)
        return messages

    def stop(self) -> None:
        for provider in self.providers:
            try:
                provider.stop()
            except Exception:
                log.exception("Chat-Quelle %s stoppt nicht sauber.", type(provider).__name__)
