"""Liest languages.yaml und erkennt links/rechts in Chat-Nachrichten.

Der Vergleich ist groß/klein-egal und bei lateinischen, griechischen,
kyrillischen und arabischen Buchstaben auch akzent-egal. "sağ" und "sag"
landen deshalb auf derselben Richtung.

Kurze Wörter mit whole_message stehen in einer eigenen Tabelle. Die
gelten nur, wenn die gesamte Nachricht genau dieses Wort ist.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from pathlib import Path

import yaml

from cave_dig.paths import project_path

# Buchstaben, die NFKD nicht zerlegt, aber als Akzent-Variante gelten sollen.
# ø bleibt sonst ø, und "højre" würde "hoyre" nicht treffen.
_EXTRA_FOLDS = str.maketrans(
    {
        "ø": "o",
        "æ": "ae",
        "å": "a",
        "ł": "l",
        "đ": "d",
        "ð": "d",
        "þ": "th",
        "ħ": "h",
        "ı": "i",
        "ŋ": "n",
        "œ": "oe",
    }
)

# Schriftbereiche, in denen Akzentzeichen nur Betonung sind und weg dürfen.
# Thai- und Devanagari-Zeichen stehen hier bewusst nicht: dort verändert
# ein Zeichen oft das ganze Wort.
_STRIP_MARK_BASE = (
    (0x0000, 0x024F),  # Basic Latin und Latin Extended
    (0x0370, 0x03FF),  # Griechisch
    (0x0400, 0x052F),  # Kyrillisch
    (0x0600, 0x06FF),  # Arabisch
    (0x1E00, 0x1EFF),  # Latin Additional (unter anderem Vietnamesisch)
)


class LanguageError(Exception):
    """languages.yaml ist kaputt oder widerspricht sich."""


@dataclass(frozen=True)
class WordEntry:
    """Ein Eintrag, wie er in der Datei steht (vor dem Vereinheitlichen)."""

    word: str
    direction: str
    lang: str
    whole_message: bool


@dataclass(frozen=True)
class LanguageTable:
    """Fertige Nachschlagetabellen. Die Spielschleife benutzt nur parse()."""

    words: tuple[WordEntry, ...]
    hints: tuple[str, ...]
    token_words: dict[str, str]
    message_words: dict[str, str]
    symbol_chars: dict[str, str]
    whole_symbols: dict[str, str]

    def parse(self, text: object) -> str | None:
        """Gibt 'left', 'right' oder None zurück. Wirft nicht.

        Eine Nachricht mit beiden Richtungen ("left right") ist ungültig,
        damit ein Witz nicht gleichzeitig beide Seiten wählt.
        """
        if not isinstance(text, str):
            return None
        cleaned = normalize_message(text)
        if not cleaned:
            return None
        # Lange Nachrichten bringen keine bessere Stimme, kosten aber Zeit.
        cleaned = cleaned[:200]

        symbol_only = self._only_symbols(cleaned)
        if symbol_only is not None:
            return symbol_only

        folded_all = fold_token(cleaned)
        if folded_all in self.message_words:
            return self.message_words[folded_all]
        # Die ganze Nachricht ist genau ein Richtungswort. Das fängt Schriften
        # ab, deren Vokalzeichen keine "Buchstaben" im engen Sinn sind.
        if " " not in cleaned and folded_all in self.token_words:
            return self.token_words[folded_all]

        found: set[str] = set()
        for token in tokenize(cleaned)[:40]:
            if token in self.symbol_chars:
                found.add(self.symbol_chars[token])
                continue
            # Variationsselektor kann am Pfeil hängen geblieben sein.
            bare = token.replace("\ufe0f", "").replace("\ufe0e", "")
            if bare in self.symbol_chars:
                found.add(self.symbol_chars[bare])
                continue
            folded = fold_token(token)
            mapped = self.token_words.get(folded)
            if mapped is not None:
                found.add(mapped)
        if len(found) == 1:
            return found.pop()
        return None

    def _only_symbols(self, text: str) -> str | None:
        """">>>" ist rechts, "<3" ist keine Stimme, "←←" ist links."""
        compact = "".join(ch for ch in text if not ch.isspace())
        if not compact:
            return None
        directions: set[str] = set()
        for ch in compact:
            direction = self.whole_symbols.get(ch)
            if direction is None:
                direction = self.symbol_chars.get(ch)
            if direction is None:
                return None
            directions.add(direction)
        if len(directions) == 1:
            return directions.pop()
        return None


def normalize_message(text: str) -> str:
    """NFKC, unsichtbare Zeichen weg, Whitespace zusammenfassen."""
    text = unicodedata.normalize("NFKC", text)
    kept = []
    for ch in text:
        if ch in ("\ufe0e", "\ufe0f"):
            continue
        if unicodedata.category(ch) == "Cf":
            continue
        kept.append(ch)
    return " ".join("".join(kept).split())


def fold_token(text: str) -> str:
    """Vereinheitlicht ein Wort für den Vergleich.

    "Sağ" und "sag" werden beide zu "sag". Thai-Tonzeichen bleiben erhalten,
    weil sie nicht in den Schriftbereichen oben liegen.
    """
    text = normalize_message(text).casefold()
    out: list[str] = []
    strip_marks = False
    for ch in unicodedata.normalize("NFKD", text):
        if unicodedata.combining(ch):
            if strip_marks:
                continue
            out.append(ch)
            continue
        out.append(ch)
        code = ord(ch)
        strip_marks = any(start <= code <= end for start, end in _STRIP_MARK_BASE)
    return "".join(out).casefold().translate(_EXTRA_FOLDS)


def tokenize(text: str) -> list[str]:
    """Zerlegt eine Nachricht in Wörter und einzelne Sonderzeichen.

    Vokalzeichen (zum Beispiel im Hindi oder Thai) bleiben am Wort kleben.
    Chinesische Zeichen ohne Leerzeichen bleiben EIN Token. "今日は左" ist
    deshalb nicht dasselbe wie das Token "左".
    """
    tokens: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            tokens.append("".join(current))
            current.clear()

    for ch in text:
        if ch.isspace():
            flush()
            continue
        category = unicodedata.category(ch)
        # L = Buchstabe, M = kombinierendes Zeichen, N = Zahl.
        if category[0] in ("L", "M", "N") or ch == "_":
            current.append(ch)
            continue
        flush()
        tokens.append(ch)
    flush()
    return tokens


def load_languages(path: Path | None = None) -> LanguageTable:
    """Lädt die YAML-Datei und bricht mit einer klaren Meldung ab, wenn zwei
    Wörter nach dem Vereinheitlichen auf verschiedene Richtungen zeigen.
    """
    file_path = path or project_path("languages.yaml")
    try:
        raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise LanguageError(f"Sprachdatei fehlt oder ist nicht lesbar: {file_path}") from exc
    except yaml.YAMLError as exc:
        raise LanguageError(f"Sprachdatei ist kein gültiges YAML: {file_path}\n{exc}") from exc
    if not isinstance(raw, dict):
        raise LanguageError("languages.yaml muss oben Schlüssel wie 'left' und 'right' haben.")

    token_words: dict[str, str] = {}
    message_words: dict[str, str] = {}
    entries: list[WordEntry] = []

    for direction in ("left", "right"):
        items = raw.get(direction) or []
        if not isinstance(items, list):
            raise LanguageError(f"'{direction}' muss eine Liste sein.")
        for item in items:
            if not isinstance(item, dict) or "word" not in item:
                raise LanguageError(f"Eintrag unter {direction} braucht ein Feld 'word'.")
            word = str(item["word"]).strip()
            if not word:
                raise LanguageError(f"Leeres Wort unter {direction}.")
            whole = bool(item.get("whole_message", False))
            lang = str(item.get("lang", ""))
            folded = fold_token(word)
            target = message_words if whole else token_words
            previous = target.get(folded)
            other = token_words.get(folded) if whole else message_words.get(folded)
            if (previous is not None and previous != direction) or (
                other is not None and other != direction
            ):
                raise LanguageError(
                    f"Das Wort '{word}' zeigt nach dem Vereinheitlichen auf zwei "
                    f"Richtungen. Bitte eines davon in languages.yaml ändern."
                )
            target[folded] = direction
            entries.append(WordEntry(word, direction, lang, whole))

    symbol_chars = _read_symbol_map(raw.get("symbols") or {}, "symbols")
    whole_symbols = _read_symbol_map(raw.get("whole_message_symbols") or {}, "whole_message_symbols")
    hints_raw = raw.get("hints") or []
    hints = tuple(str(item) for item in hints_raw if str(item).strip())
    return LanguageTable(
        words=tuple(entries),
        hints=hints,
        token_words=token_words,
        message_words=message_words,
        symbol_chars=symbol_chars,
        whole_symbols=whole_symbols,
    )


def _read_symbol_map(section: object, label: str) -> dict[str, str]:
    if not isinstance(section, dict):
        raise LanguageError(f"'{label}' muss eine Zuordnung left/right sein.")
    mapping: dict[str, str] = {}
    for direction in ("left", "right"):
        values = section.get(direction) or []
        if not isinstance(values, list):
            raise LanguageError(f"'{label}.{direction}' muss eine Liste sein.")
        for value in values:
            for ch in str(value):
                # Variationsselektor nicht als eigenes Zeichen speichern.
                if ch in ("\ufe0e", "\ufe0f"):
                    continue
                mapping[ch] = direction
    return mapping
