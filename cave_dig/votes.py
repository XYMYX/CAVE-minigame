"""Sammelt Stimmen in kurzen Zeitfenstern und nimmt die Mehrheit.

Eine einzelne Nachricht soll den Lauf nicht sofort reißen. Darum sammeln
wir zum Beispiel 2,5 Sekunden lang und schieben die Spitzhacke erst dann.
Pro Fenster zählt jede Person nur einmal (die letzte Richtung gewinnt),
damit jemand mit einem Makro nicht zehnmal zählt.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VoteResult:
    """Ergebnis eines abgeschlossenen Fensters."""

    winner: str | None
    left: int
    right: int
    voters_left: tuple[str, ...]
    voters_right: tuple[str, ...]

    def credit_names(self) -> list[str]:
        """Wer Punkte aus diesem Fenster bekommt.

        Die Gewinnerseite teilt sich die Punkte. Bei Gleichstand teilen
        alle, die abgestimmt haben: Mitmachen soll sich lohnen, auch wenn
        die Spitzhacke nicht ausschlägt.
        """
        if self.winner == "left":
            return list(self.voters_left)
        if self.winner == "right":
            return list(self.voters_right)
        return list(self.voters_left) + list(self.voters_right)

    def all_voters(self) -> list[str]:
        return list(self.voters_left) + list(self.voters_right)


class VoteAggregator:
    """Zählt Personen je Richtung innerhalb des aktuellen Fensters."""

    def __init__(self, window_seconds: float, one_per_user: bool) -> None:
        if window_seconds <= 0:
            raise ValueError("vote_window_seconds muss größer als 0 sein.")
        self.window_seconds = window_seconds
        self.one_per_user = one_per_user
        self.window_start = 0.0
        # Liste statt Zähler, damit "eine Person, eine Stimme" die alte
        # Richtung ersetzen kann und wir die Namen für die Bestenliste behalten.
        self.entries: list[tuple[str, str]] = []

    def reset(self, now: float) -> None:
        """Neues Fenster, alte Stimmen weg. Zum Rundenstart."""
        self.window_start = now
        self.entries.clear()

    @property
    def left(self) -> int:
        return sum(1 for _name, direction in self.entries if direction == "left")

    @property
    def right(self) -> int:
        return sum(1 for _name, direction in self.entries if direction == "right")

    def progress(self, now: float) -> float:
        """0 am Anfang des Fensters, 1 direkt vor dem Auszählen."""
        span = self.window_seconds
        if span <= 0:
            return 1.0
        done = (now - self.window_start) / span
        if done < 0:
            return 0.0
        if done > 1:
            return 1.0
        return done

    def add(self, author: str, direction: str, now: float) -> list[VoteResult]:
        """Hängt eine Stimme an. Schließt vorher alle fälligen Fenster."""
        closed = self.close_due(now)
        if direction not in ("left", "right"):
            return closed
        if self.one_per_user:
            self.entries = [(name, old) for name, old in self.entries if name != author]
        self.entries.append((author, direction))
        return closed

    def close_due(self, now: float) -> list[VoteResult]:
        """Schließt Fenster, deren Zeit um ist. Höchstens ein paar Stück,
        falls das Spiel kurz geruckelt hat. Sonst würde ein Hänger eine
        Lawine leerer Fenster erzeugen.
        """
        results: list[VoteResult] = []
        closed = 0
        while now + 1e-9 >= self.window_start + self.window_seconds and closed < 5:
            results.append(self._close())
            self.window_start += self.window_seconds
            closed += 1
        if now + 1e-9 >= self.window_start + self.window_seconds:
            self.window_start = now
            self.entries.clear()
        return results

    def close_now(self) -> VoteResult:
        """Zählt das offene Fenster sofort aus. Zum Rundenende."""
        return self._close()

    def _close(self) -> VoteResult:
        left_names = [name for name, direction in self.entries if direction == "left"]
        right_names = [name for name, direction in self.entries if direction == "right"]
        winner: str | None = None
        if len(left_names) > len(right_names):
            winner = "left"
        elif len(right_names) > len(left_names):
            winner = "right"
        self.entries.clear()
        # Für die Punkte zählen Personen, nicht jede Wiederholung.
        return VoteResult(
            winner,
            len(left_names),
            len(right_names),
            tuple(sorted(set(left_names))),
            tuple(sorted(set(right_names))),
        )
