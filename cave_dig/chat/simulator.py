"""Tastaturersatz: Bots schreiben zufällige Richtungswörter.

So kannst du das Spiel starten, ohne einen YouTube-Schlüssel zu haben.
Die Wörter kommen aus languages.yaml. Eine neue Sprache üben die Bots
also mit, sobald sie in der Datei steht.

Die echten Pfeiltasten fängt das Fenster ab und gibt sie als lokale
Stimme ins Spiel. Dieser Anbieter erzeugt nur die Bot-Zeilen.
"""

from __future__ import annotations

import random

from cave_dig.chat.base import ChatMessage, ChatProvider
from cave_dig.config import GameConfig
from cave_dig.i18n import load_catalog
from cave_dig.languages import LanguageTable, WordEntry

_NAMES = (
    "Nora",
    "Kenji",
    "Lina",
    "Omar",
    "Sven",
    "Aisha",
    "Theo",
    "Maja",
    "Rin",
    "Pavel",
    "Noor",
    "Levi",
    "Hana",
    "Idris",
)
_JUNK = ("haha", "gg", "lol", "nice", "oh nein", "weiter", "...")
_TEMPLATES = ("{w}", "{w}", "{w}!", "{w}!!", "go {w}", "{w} bitte")


class SimulatorProvider(ChatProvider):
    def __init__(
        self,
        config: GameConfig,
        languages: LanguageTable,
        *,
        seed: int,
        demo: bool,
    ) -> None:
        super().__init__()
        self.config = config
        self.languages = languages
        self.demo = demo
        self.rng = random.Random(seed or 1)
        self.bot_enabled = config.bot_enabled
        self.interval_min = 0.12 if demo else config.bot_interval_min
        self.interval_max = 0.30 if demo else config.bot_interval_max
        if self.interval_max < self.interval_min:
            self.interval_max = self.interval_min
        self.bias_left = 0.64 if demo else config.bot_bias_left
        self._words = list(languages.words)
        self._left = [entry for entry in self._words if entry.direction == "left"] or self._words
        self._right = [entry for entry in self._words if entry.direction == "right"] or self._words
        self.next_bot = self.interval_min
        self._status = load_catalog(config.language, config.locales_dir).t("status.simulator")

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def poll(self, now: float) -> list[ChatMessage]:
        if not self.bot_enabled or not self._words:
            return []
        messages: list[ChatMessage] = []
        guard = 0
        while now >= self.next_bot and guard < 8:
            guard += 1
            messages.append(self._one(now))
            span = self.rng.uniform(self.interval_min, self.interval_max)
            self.next_bot = now + max(0.05, span)
        return messages

    def _one(self, now: float) -> ChatMessage:
        author = self.rng.choice(_NAMES)
        roll = self.rng.random()
        # Im Demolauf keine Zufalls-Ereignisse, sonst verdeckt das Banner
        # die Höhle auf den Beispielbildern.
        if not self.demo and roll < 0.06:
            text = "!event"
        elif roll < 0.1:
            text = self.rng.choice(_JUNK)
        elif roll < 0.14:
            text = "left right"
        else:
            pool = self._left if self.rng.random() < self.bias_left else self._right
            text = _phrase(self.rng, self.rng.choice(pool))
        return ChatMessage(author, text, now)


def _phrase(rng: random.Random, entry: WordEntry) -> str:
    word = entry.word
    if word.isascii() and word.isalpha() and rng.random() < 0.22:
        word = word.upper()
    if entry.whole_message:
        return word
    return rng.choice(_TEMPLATES).format(w=word)
