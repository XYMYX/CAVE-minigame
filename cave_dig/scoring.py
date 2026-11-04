"""Punkte, Bestenliste und das Aufteilen auf Chat-Namen.

Der Rundenscore steigt sofort, wenn ein Block bricht. Die Namen auf der
Bestenliste bekommen ihren Anteil erst, wenn das Stimmen-Fenster schließt.
So sieht man den Punktestand live, und die "Gräber" gehören zu den Leuten,
die in dem Moment wirklich abgestimmt haben.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("cave_dig.score")


def points_at_depth(base: int, depth_m: int, per_meter: float, cap: float) -> int:
    """Tiefe macht Blöcke etwas wertvoller, aber nicht unbegrenzt."""
    if base <= 0:
        return 0
    multiplier = min(cap, 1.0 + max(0, depth_m) * per_meter)
    return max(1, int(round(base * multiplier)))


def split_points(total: int, names: list[str]) -> dict[str, int]:
    """Teilt Punkte möglichst gleich auf. Der Rest geht an die ersten Namen
    in alphabetischer Reihenfolge, damit das Ergebnis in Tests stabil ist.
    """
    if total <= 0 or not names:
        return {}
    ordered = sorted(set(names))
    base, remainder = divmod(total, len(ordered))
    shares: dict[str, int] = {}
    for index, name in enumerate(ordered):
        shares[name] = base + (1 if index < remainder else 0)
    return shares


@dataclass
class Contributor:
    name: str
    points: int = 0
    votes: int = 0


@dataclass
class Scoreboard:
    """Bleibt über Runden hinweg erhalten und wird auf die Platte geschrieben."""

    high_score: int = 0
    best_depth: int = 0
    rounds_played: int = 0
    round_score: int = 0
    contributors: dict[str, Contributor] = field(default_factory=dict)

    def add_round_points(self, points: int) -> None:
        if points > 0:
            self.round_score += points

    def add_contributor_points(self, name: str, points: int) -> None:
        if points <= 0:
            return
        entry = self.contributors.setdefault(name, Contributor(name))
        entry.points += points

    def add_vote(self, name: str) -> None:
        entry = self.contributors.setdefault(name, Contributor(name))
        entry.votes += 1

    def finish_round(self, depth: int) -> None:
        """Rekord prüfen, Runde zählen, Rundenscore zurücksetzen.

        Die Bestenliste bleibt. Die ist das Gedächtnis über viele Runden.
        """
        if self.round_score > self.high_score:
            self.high_score = self.round_score
        if depth > self.best_depth:
            self.best_depth = depth
        self.rounds_played += 1
        self.round_score = 0

    def top(self, limit: int = 5) -> list[Contributor]:
        ranked = sorted(
            self.contributors.values(),
            key=lambda entry: (-entry.points, -entry.votes, entry.name.casefold()),
        )
        return ranked[:limit]

    def prune(self, limit: int = 200) -> None:
        """Ein Dauerstream sieht viele Namen. Wir behalten die besten."""
        if len(self.contributors) <= limit:
            return
        kept = self.top(limit)
        self.contributors = {entry.name: entry for entry in kept}


def save_scoreboard(path: Path, board: Scoreboard) -> None:
    """Schreibt erst eine Temp-Datei und benennt sie dann um.

    Wenn der PC mitten im Schreiben ausgeht, bleibt die alte Datei ganz.
    Ein halbfertiges JSON würde beim nächsten Start nur Ärger machen.
    """
    board.prune()
    payload = {
        "version": 1,
        "high_score": board.high_score,
        "best_depth": board.best_depth,
        "rounds_played": board.rounds_played,
        "contributors": [
            {"name": entry.name, "points": entry.points, "votes": entry.votes}
            for entry in board.contributors.values()
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def load_scoreboard(path: Path) -> Scoreboard:
    """Lädt den Stand. Eine kaputte Datei ist kein Abbruch, sondern ein Neuanfang.

    Die kaputte Datei wird beiseitegelegt. Sonst überschreibt das nächste
    Speichern den alten Rekord, und man könnte ihn nicht mehr von Hand retten.
    """
    if not path.exists():
        return Scoreboard()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError) as exc:
        # ValueError deckt kaputtes JSON und ungültiges UTF-8 ab.
        log.warning("Speicherdatei unlesbar (%s). Starte ohne Rekord.", exc)
        _set_aside(path)
        return Scoreboard()
    if not isinstance(raw, dict):
        log.warning("Speicherdatei hat das falsche Format. Starte ohne Rekord.")
        _set_aside(path)
        return Scoreboard()
    board = Scoreboard(
        high_score=_nonneg_int(raw.get("high_score")),
        best_depth=_nonneg_int(raw.get("best_depth")),
        rounds_played=_nonneg_int(raw.get("rounds_played")),
    )
    items = raw.get("contributors") or []
    if not isinstance(items, list):
        log.warning("Bestenliste in der Speicherdatei ist unlesbar. Starte ohne Namen.")
        _set_aside(path)
        items = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        entry = Contributor(
            name=name[:24],
            points=_nonneg_int(item.get("points")),
            votes=_nonneg_int(item.get("votes")),
        )
        board.contributors[entry.name] = entry
    return board


def _set_aside(path: Path) -> None:
    """Benennt stand.json in stand.broken.json um, falls das geht."""
    backup = path.with_suffix(".broken" + path.suffix)
    try:
        path.replace(backup)
    except OSError as exc:
        log.warning("Kaputte Speicherdatei nicht beiseitegelegt: %s", exc)
        return
    log.warning("Kaputte Speicherdatei liegt jetzt unter %s.", backup)


def _nonneg_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(0, value)
