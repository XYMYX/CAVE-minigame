"""Erkennt !event im Chat, bevor der Text als Stimme gilt.

"!event" allein würfelt ein Ereignis. "!event einsturz" sucht den Namen
in der Alias-Liste aus config.yaml. Großschreibung ist egal.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedCommand:
    event_id: str | None
    unknown: str | None


def parse_event_command(
    text: object,
    command: str,
    aliases: dict[str, str],
) -> ParsedCommand | None:
    """None, wenn die Nachricht kein Befehl ist."""
    if not isinstance(text, str):
        return None
    raw = " ".join(text.strip().split())
    if not raw:
        return None
    prefix = command.strip().casefold()
    folded = raw.casefold()
    if not folded.startswith(prefix):
        return None
    # Nur als Befehl werten, wenn danach Ende oder ein Leerzeichen kommt.
    # "!eventuell" soll nicht aus Versehen ein Ereignis starten.
    if len(folded) > len(prefix) and not folded[len(prefix)].isspace():
        return None
    rest = folded[len(prefix) :].strip()
    if not rest:
        return ParsedCommand(event_id=None, unknown=None)
    token = rest.split()[0].strip("!.,:;")
    if token in ("random", "zufall", "mix"):
        return ParsedCommand(event_id=None, unknown=None)
    event_id = aliases.get(token)
    if event_id is None:
        return ParsedCommand(event_id=None, unknown=token)
    return ParsedCommand(event_id=event_id, unknown=None)
