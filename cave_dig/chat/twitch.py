"""Twitch-Chat über IRC mit TLS, nur lesend und ohne Token.

IRC ist ein altes Textprotokoll: Der Server schickt Zeile für Zeile, wir
lesen mit. Der Ablauf:

  1. Verbinden mit irc.chat.twitch.tv, Port 6697 (TLS).
  2. Senden, was login_lines() baut: Tags anfordern, als Gast anmelden,
     dem Kanal beitreten.
  3. Zeilen lesen. Eine Chatzeile sieht so aus:
       @user-id=123;display-name=Nora :nora!nora@nora.tmi.twitch.tv PRIVMSG #kanal :links
  4. Chatzeilen als ChatMessage in eine Warteschlange legen. poll() leert sie.
  5. Bei einem Abbruch warten und neu verbinden. Keine Ausnahme erreicht das Spiel.

Gast heisst: Der Name justinfan plus Zahl braucht kein Konto und darf nur
lesen. Die offizielle Doku von Twitch nennt nur die Anmeldung mit Token. Der
Gastzugang ist verbreitet, aber nicht zugesichert. Falls Twitch ihn abstellt,
ändert sich nur login_lines(): Dort käme PASS oauth:DEIN_TOKEN und dein
Botname hinein. Der Rest bleibt gleich.

Alle Zeiten stehen als Konstanten direkt unter den Importen.
"""

from __future__ import annotations

import logging
import random
import re
import socket
import ssl
import threading
import time
from dataclasses import dataclass

from cave_dig.chat.base import ChatMessage, ChatProvider
from cave_dig.config import GameConfig
from cave_dig.i18n import Catalog, load_catalog

log = logging.getLogger("cave_dig.twitch")

HOST = "irc.chat.twitch.tv"
PORT = 6697
CONNECT_TIMEOUT = 15.0
# So oft schaut der Thread nach, ob er aufhören soll.
READ_WAIT = 1.0
# Twitch antwortet nicht, wenn es den Kanal nicht gibt. Darum selbst aufgeben.
JOIN_TIMEOUT = 30.0
# Twitch pingt etwa alle 5 Minuten, auch in einem stillen Chat.
# Kommt länger gar nichts, ist die Verbindung tot.
SILENCE_LIMIT = 360.0
BACKOFF_START = 5.0
BACKOFF_MAX = 300.0
NO_CHANNEL_WAIT = 20.0
MAX_QUEUE = 400
MAX_LINE_BYTES = 65_536

_CHANNEL = re.compile(r"[a-z0-9_]{1,25}")
_TAG_ESCAPE = re.compile(r"\\(.?)")
_TAG_VALUES = {"s": " ", ":": ";", "r": "\r", "n": "\n", "\\": "\\"}


@dataclass(frozen=True)
class IrcLine:
    """Eine Serverzeile, in ihre Teile zerlegt."""

    tags: dict[str, str]
    prefix: str
    command: str
    params: tuple[str, ...]


def normalize_channel(value: str) -> str:
    """Nimmt einen Kanalnamen oder eine ganze Twitch-Adresse. Ungültig ergibt ""."""
    text = value.strip().lower().lstrip("#")
    if "twitch.tv/" in text:
        text = text.split("twitch.tv/", 1)[1]
    text = text.split("?", 1)[0].split("/", 1)[0]
    return text if _CHANNEL.fullmatch(text) else ""


def login_lines(channel: str) -> list[str]:
    """Die Zeilen für die Anmeldung. Der einzige Ort, der sie kennt."""
    return [
        "CAP REQ :twitch.tv/tags twitch.tv/commands",
        "PASS SCHMOOPIIE",
        f"NICK justinfan{random.randint(10_000, 99_999)}",
        f"JOIN #{channel}",
    ]


def parse_irc_line(line: str) -> IrcLine | None:
    """Zerlegt eine Zeile. Gibt None zurück, wenn kein Befehl darin steht."""
    rest = line.strip("\r\n")
    tags: dict[str, str] = {}
    if rest.startswith("@"):
        raw_tags, _, rest = rest.partition(" ")
        tags = _parse_tags(raw_tags[1:])
    prefix = ""
    if rest.startswith(":"):
        prefix, _, rest = rest[1:].partition(" ")
    # Hinter dem ersten " :" steht der freie Text. Er darf selbst Doppelpunkte enthalten.
    head, has_text, text = rest.partition(" :")
    parts = head.split()
    if not parts:
        return None
    params = parts[1:] + ([text] if has_text else [])
    return IrcLine(tags, prefix, parts[0].upper(), tuple(params))


def _parse_tags(raw: str) -> dict[str, str]:
    tags: dict[str, str] = {}
    for item in raw.split(";"):
        key, _, value = item.partition("=")
        if key:
            tags[key] = _TAG_ESCAPE.sub(lambda m: _TAG_VALUES.get(m[1], m[1]), value)
    return tags


def chat_message_from(line: IrcLine) -> ChatMessage | None:
    """Macht aus einer Chatzeile eine ChatMessage. Alles andere ergibt None."""
    if line.command != "PRIVMSG" or len(line.params) < 2:
        return None
    text = line.params[-1]
    # /me-Zeilen sind in das Steuerzeichen 0x01 verpackt. Sie sind keine Stimmen.
    if text.startswith("\x01"):
        return None
    # Ohne feste Nummer würde das Spiel die Person über den Namen zählen.
    user_id = line.tags.get("user-id", "").strip()
    if not user_id:
        return None
    author = line.tags.get("display-name") or line.prefix.split("!", 1)[0]
    return ChatMessage(author, text, _sent_at(line.tags), f"twitch:{user_id}")


def _sent_at(tags: dict[str, str]) -> float:
    """tmi-sent-ts steht in Millisekunden."""
    try:
        return int(tags.get("tmi-sent-ts", "")) / 1000.0
    except ValueError:
        return 0.0


class TwitchChatProvider(ChatProvider):
    def __init__(self, config: GameConfig) -> None:
        super().__init__()
        self._catalog: Catalog = load_catalog(config.language, config.locales_dir)
        self.channel = normalize_channel(config.twitch_channel)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._queue: list[ChatMessage] = []
        self._lock = threading.Lock()
        self._joined = False
        self._set_status("twitch_connecting")

    def start(self) -> None:
        # Daemon: wenn das Fenster zu ist, hält der Thread den Prozess nicht fest.
        self._thread = threading.Thread(target=self._run, name="twitch-chat", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def poll(self, now: float) -> list[ChatMessage]:
        with self._lock:
            items = self._queue
            self._queue = []
            return items

    def _set_status(self, key: str) -> None:
        self._status = self._catalog.t(f"status.{key}")

    def _push(self, message: ChatMessage) -> None:
        with self._lock:
            self._queue.append(message)
            if len(self._queue) > MAX_QUEUE:
                self._queue = self._queue[-MAX_QUEUE:]

    def _run(self) -> None:
        backoff = BACKOFF_START
        while not self._stop.is_set():
            if not self.channel:
                self._set_status("twitch_missing")
                log.error(self._status)
                self._stop.wait(NO_CHANNEL_WAIT)
                continue
            self._joined = False
            self._set_status("twitch_connecting")
            try:
                with self._connect() as connection:
                    self._session(connection)
            except Exception as exc:
                log.warning("Twitch-Verbindung unterbrochen: %s", exc)
            if self._stop.is_set():
                return
            # Erst ein bestätigter Beitritt setzt die Wartezeit zurück. Sonst
            # würde ein Fehler direkt nach dem Verbinden Twitch im Takt anklopfen.
            if self._joined:
                backoff = BACKOFF_START
            self._set_status("twitch_other")
            self._stop.wait(backoff)
            backoff = min(BACKOFF_MAX, backoff * 2)

    def _connect(self) -> socket.socket:
        # Eigene Zeitlimits. YouTube setzt prozessweit einen anderen Standardwert.
        raw = socket.create_connection((HOST, PORT), timeout=CONNECT_TIMEOUT)
        try:
            secure = ssl.create_default_context().wrap_socket(raw, server_hostname=HOST)
        except Exception:
            raw.close()
            raise
        secure.settimeout(READ_WAIT)
        return secure

    def _session(self, connection: socket.socket) -> None:
        """Liest, bis die Verbindung endet. Kehrt zurück oder wirft, nie beides ins Spiel."""
        for line in login_lines(self.channel):
            _send(connection, line)
        started = last_data = time.monotonic()
        buffer = b""
        while not self._stop.is_set():
            now = time.monotonic()
            if now - last_data > SILENCE_LIMIT:
                raise ConnectionError("Zu lange keine Daten von Twitch.")
            if not self._joined and now - started > JOIN_TIMEOUT:
                raise ConnectionError(f"Kein Beitritt zu #{self.channel}. Stimmt der Kanalname?")
            try:
                chunk = connection.recv(4096)
            except TimeoutError:
                continue
            if not chunk:
                raise ConnectionError("Twitch hat die Verbindung geschlossen.")
            last_data = time.monotonic()
            buffer += chunk
            if len(buffer) > MAX_LINE_BYTES and b"\n" not in buffer:
                buffer = b""
            *lines, buffer = buffer.split(b"\n")
            for raw_line in lines:
                if not self._handle_line(connection, raw_line.decode("utf-8", "replace")):
                    return

    def _handle_line(self, connection: socket.socket, text: str) -> bool:
        """Verarbeitet eine Zeile. False heisst: Twitch will, dass wir neu verbinden."""
        line = parse_irc_line(text)
        if line is None:
            return True
        if line.command == "PING":
            _send(connection, f"PONG :{line.params[-1]}" if line.params else "PONG")
        elif line.command == "RECONNECT":
            log.info("Twitch bittet um eine neue Verbindung.")
            return False
        elif line.command in ("JOIN", "ROOMSTATE"):
            if not self._joined:
                self._joined = True
                self._set_status("twitch_ready")
                log.info("Twitch-Chat von #%s verbunden.", self.channel)
        else:
            message = chat_message_from(line)
            if message is not None:
                self._push(message)
        return True


def _send(connection: socket.socket, line: str) -> None:
    connection.sendall(f"{line}\r\n".encode("utf-8"))
