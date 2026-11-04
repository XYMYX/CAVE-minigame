"""Kleine Helfer ohne Pygame.

Die Spiellogik soll auch in Tests laufen, ohne ein Fenster zu öffnen.
Darum liegen Formatierung und Namens-Bereinigung hier und nicht im Renderer.
"""

from __future__ import annotations


def clamp(value: float, low: float, high: float) -> float:
    """Begrenzt eine Zahl auf einen Bereich. Wie std::clamp in C++."""
    if value < low:
        return low
    if value > high:
        return high
    return value


def format_int(value: int) -> str:
    """12345 wird zu 12.345, also mit deutschem Tausenderpunkt."""
    return f"{int(value):,}".replace(",", ".")


def sanitize_name(name: object, fallback: str = "Unknown") -> str:
    """Macht einen Chat-Namen anzeigbar und speicherbar.

    Zuschauer können seltsame Zeichen schicken. Wir behalten druckbare
    Zeichen, schneiden auf 24 Zeichen und ersetzen leere Namen. So landet
    kein Zeilenumbruch im Log oder in der Speicherdatei. fallback kommt
    aus der Sprachdatei (hud.unknown).
    """
    spare = fallback.strip()[:24] or "Unknown"
    if not isinstance(name, str):
        return spare
    cleaned = "".join(ch for ch in name if ch.isprintable())
    cleaned = " ".join(cleaned.split()).strip()
    if not cleaned:
        return spare
    return cleaned[:24]


def lerp_color(
    a: tuple[int, int, int],
    b: tuple[int, int, int],
    t: float,
) -> tuple[int, int, int]:
    """Mischt zwei Farben. t = 0 ist a, t = 1 ist b."""
    t = clamp(t, 0.0, 1.0)
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
