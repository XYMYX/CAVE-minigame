"""Gemeinsame Form für jede Chat-Quelle.

Das Spiel fragt poll() und bekommt Nachrichten. Es weiß nicht, ob die
von der Tastatur, von Bots oder von YouTube kommen. Eine neue Quelle
ist eine Klasse mit start, poll und stop.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ChatMessage:
    author: str
    text: str
    sent_at: float = 0.0
    # Feste Kennung vom Anbieter. Anzeigenamen sind nicht eindeutig.
    author_id: str = ""


class ChatProvider(ABC):
    """start einmal, poll jeden Frame, stop beim Beenden."""

    def __init__(self) -> None:
        self._status = ""

    @property
    def status(self) -> str:
        return self._status

    @abstractmethod
    def start(self) -> None:
        """Verbindung aufmachen. Darf nicht ewig blockieren."""

    @abstractmethod
    def poll(self, now: float) -> list[ChatMessage]:
        """Neue Nachrichten seit dem letzten Aufruf. Wirft nicht."""

    @abstractmethod
    def stop(self) -> None:
        """Verbindung zu. Danach kommt kein poll mehr."""
