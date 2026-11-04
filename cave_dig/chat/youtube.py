"""YouTube-Live-Chat über die offizielle Data API v3.

Zwei Wege, beide in config.yaml unter chat.youtube.mode:

  api_key   API-Schlüssel plus Video-ID. Der Schlüssel darf nur lesen.
  oauth     Einmal anmelden (python -m cave_dig.auth). Danach sucht das
            Spiel deinen gerade laufenden Livestream selbst.

liveChatMessages.list kostet 5 Kontingent-Einheiten pro Aufruf. Das
normale Tageslimit liegt bei 10.000 Einheiten. Für einen Stream rund um
die Uhr heißt das: nicht alle paar Sekunden fragen. Der Standard von
50 Sekunden liegt bei etwa 8.640 Einheiten am Tag, plus ein paar Aufrufe
zum Finden des Chats. Die API schickt selbst ein pollingIntervalMillis.
Wir warten mindestens so lang wie die API will, und mindestens so lang
wie min_poll_seconds. Lieber etwas später als gesperrt.

Nachrichten kommen deshalb in Bündeln. Das Stimmen-Fenster zählt sie,
sobald sie ankommen. Der Balken im Bild reagiert auf dieses Bündel.

Mit chat.youtube.transport: stream (Standard) bleibt stattdessen eine
Verbindung offen, siehe youtube_stream.py. Stimmen kommen dann sofort. Laut
YouTube kostet ein Aufruf 5 Einheiten. Bricht die Verbindung ab, wartet das
Spiel min_poll_seconds bis zum nächsten Versuch. Im schlimmsten Fall kostet
der Stream darum gleich viel wie die Abfrage, nicht mehr.

Fehler (Netz, Limit, Stream aus) beenden das Spiel nicht. Der Thread
wartet und versucht es wieder.
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from datetime import datetime, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from cave_dig.chat.base import ChatMessage, ChatProvider
from cave_dig.config import GameConfig
from cave_dig.i18n import Catalog, load_catalog

log = logging.getLogger("cave_dig.youtube")

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]
_QUOTA_WAIT = 15 * 60
_RATE_WAIT = 30


def normalize_video_id(value: str) -> str:
    """Nimmt eine nackte ID oder eine ganze Watch-URL."""
    text = value.strip()
    if "youtu.be/" in text:
        text = text.split("youtu.be/", 1)[1]
        return text.split("?", 1)[0].split("&", 1)[0].strip("/")
    if "live/" in text and "youtube" in text:
        text = text.split("live/", 1)[1]
        return text.split("?", 1)[0].split("&", 1)[0].strip("/")
    if "v=" in text:
        text = text.split("v=", 1)[1]
        return text.split("&", 1)[0].strip()
    return text.strip()


def parse_live_chat_payload(
    payload: dict,
) -> tuple[list[ChatMessage], str | None, float | None]:
    """Holt Nachrichten, den nächsten Seiten-Stempel und die Wartezeit heraus.

    Eine kaputte einzelne Nachricht wird übersprungen. Der Rest zählt.
    """
    messages: list[ChatMessage] = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        try:
            snippet = item.get("snippet") or {}
            # Nur echte Textnachrichten. Sperr-Meldungen, Mitgliedschaften und
            # Ähnliches haben auch einen Anzeigetext, sind aber keine Stimmen.
            if snippet.get("type", "textMessageEvent") != "textMessageEvent":
                continue
            if "displayMessage" not in snippet:
                continue
            details = item.get("authorDetails") or {}
            author = details.get("displayName") or ""
            channel = details.get("channelId")
            text = snippet.get("displayMessage")
            messages.append(
                ChatMessage(
                    str(author),
                    str(text),
                    _published(snippet.get("publishedAt")),
                    f"youtube:{channel}" if channel else "",
                )
            )
        except Exception:
            log.info("Eine Chat-Zeile war unlesbar und wird übersprungen.")
    token = payload.get("nextPageToken")
    token_text = str(token) if token else None
    wait_ms = payload.get("pollingIntervalMillis")
    wait = float(wait_ms) / 1000.0 if isinstance(wait_ms, (int, float)) else None
    return messages, token_text, wait


def classify_api_error(status: int, body: str) -> str:
    """Ordnet eine HTTP-Antwort einem kurzen Grund zu. Der Thread entscheidet die Pause."""
    text = body or ""
    lowered = text.lower()
    if "quotaexceeded" in lowered or "dailylimitexceeded" in lowered:
        return "quota"
    if status == 429 or "ratelimitexceeded" in lowered:
        return "rate"
    if "livechatended" in lowered or "livechatnotfound" in lowered or "videonotfound" in lowered:
        return "ended"
    if status == 404:
        return "not_found"
    if status in (401, 403):
        return "auth"
    return "other"


class StreamFailed(Exception):
    """Die offene Verbindung ist mit einem Fehler von YouTube abgebrochen."""

    def __init__(self, kind: str, code: str, details: str) -> None:
        super().__init__(f"{code} ({kind})")
        self.kind = kind
        self.code = code
        self.details = details


class YouTubeChatProvider(ChatProvider):
    def __init__(self, config: GameConfig) -> None:
        super().__init__()
        self.config = config
        self._catalog: Catalog = load_catalog(config.language, config.locales_dir)
        self.mode = config.youtube_mode
        self.transport = config.youtube_transport
        self.api_key = config.youtube_api_key
        self.video_id = normalize_video_id(config.youtube_video_id)
        self.min_poll = config.youtube_min_poll_seconds
        self.secrets_path = config.youtube_client_secrets
        self.token_path = config.youtube_token_path
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._queue: list[ChatMessage] = []
        self._lock = threading.Lock()
        self._client = None
        self._credentials: Credentials | None = None
        self._channel = None
        self._call = None
        self._next_connect = 0.0
        self.chat_id: str | None = None
        self.page_token: str | None = None
        self.primed = False
        self._warned_interval = False
        self._status = self._catalog.t("status.connecting")

    def start(self) -> None:
        # Daemon: wenn das Fenster zu ist, hält der Thread den Prozess nicht fest.
        # stop() weckt ihn trotzdem, damit die Verbindung sauber endet.
        self._thread = threading.Thread(target=self._run, name="youtube-chat", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        call = self._call
        if call is not None:
            # Eine offene Verbindung wartet sonst weiter auf die nächste Nachricht.
            call.cancel()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def poll(self, now: float) -> list[ChatMessage]:
        with self._lock:
            items = self._queue
            self._queue = []
            return items

    def _set_status(self, key: str) -> None:
        self._status = self._catalog.t(f"status.{key}")

    def _push(self, messages: list[ChatMessage]) -> None:
        if not messages:
            return
        with self._lock:
            self._queue.extend(messages)
            # Ein Bündel kann groß sein. Wir behalten die neuesten 400.
            if len(self._queue) > 400:
                self._queue = self._queue[-400:]

    def _run(self) -> None:
        # Verhindert, dass ein hängender API-Aufruf den Thread für immer blockiert.
        socket.setdefaulttimeout(30)
        backoff = 5.0
        while not self._stop.is_set():
            problem = self._missing_setup()
            if problem:
                self._set_status(problem)
                log.error(self._status)
                self._stop.wait(20)
                continue
            try:
                if self._client is None:
                    self._client = self._build_client()
                if not self.chat_id:
                    self._set_status("connecting")
                    self.chat_id = self._resolve_chat_id()
                    self.page_token = None
                    self.primed = False
                    log.info("Live-Chat gefunden.")
                if self.transport == "stream":
                    self._stream_once()
                    backoff = 5.0
                    continue
                wait = self._poll_once()
                backoff = 5.0
                pause = max(self.min_poll, wait or 0)
                if wait and wait + 1 < self.min_poll and not self._warned_interval:
                    log.info(
                        "Die API würde alle %.0f s erlauben. Wir warten %.0f s, "
                        "damit das Tageslimit für einen Dauerstream reicht.",
                        wait,
                        self.min_poll,
                    )
                    self._warned_interval = True
                self._set_status("ready")
                self._stop.wait(pause)
            except RuntimeError as exc:
                # Zum Beispiel: Stream ist noch nicht live. Kein Abbruch.
                self._set_status("ended")
                log.info("%s", exc)
                self.chat_id = None
                self.page_token = None
                self.primed = False
                self._stop.wait(20)
            except HttpError as exc:
                body = exc.content.decode("utf-8", "replace") if exc.content else ""
                status = getattr(exc.resp, "status", 0) or 0
                backoff = self._after_failure(
                    classify_api_error(int(status), body), status, body, backoff
                )
            except StreamFailed as exc:
                backoff = self._after_failure(exc.kind, exc.code, exc.details, backoff)
            except Exception as exc:
                self._set_status("other")
                log.exception("YouTube-Verbindung unterbrochen: %s", exc)
                self.chat_id = None
                self._client = None
                self._stop.wait(min(300.0, backoff))
                backoff = min(300.0, backoff * 2)
        self._close_channel()

    def _after_failure(self, kind: str, status: object, body: str, backoff: float) -> float:
        """Setzt Anzeige und Zustand, wartet und gibt die nächste Pause zurück."""
        self._set_status(kind)
        log.warning("YouTube-Fehler %s (%s): %s", status, kind, body[:300])
        delay = self._delay_for(kind, backoff)
        if kind == "other":
            backoff = min(300.0, backoff * 2)
        if kind in ("ended", "not_found", "auth"):
            self.chat_id = None
            self.page_token = None
            self.primed = False
        if kind == "auth":
            self._client = None
        self._stop.wait(delay)
        return backoff

    def _delay_for(self, kind: str, backoff: float) -> float:
        if kind == "quota":
            return _QUOTA_WAIT
        if kind == "rate":
            return _RATE_WAIT
        if kind in ("ended", "not_found"):
            return 20
        if kind == "auth":
            return 60
        return min(300.0, backoff)

    def _missing_setup(self) -> str | None:
        if self.mode == "oauth":
            if not self.token_path.exists():
                return "oauth_missing"
            return None
        if not self.api_key or not self.video_id:
            return "missing"
        return None

    def _build_client(self):
        if self.mode == "oauth":
            self._credentials = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
            return build(
                "youtube", "v3", credentials=self._fresh_credentials(), cache_discovery=False
            )
        return build("youtube", "v3", developerKey=self.api_key, cache_discovery=False)

    def _fresh_credentials(self) -> Credentials:
        creds = self._credentials
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_path.write_text(creds.to_json(), encoding="utf-8")
        if not creds.valid:
            raise RuntimeError("OAuth-Token ist ungültig. python -m cave_dig.auth erneut ausführen.")
        return creds

    def _resolve_chat_id(self) -> str:
        if self.mode == "oauth":
            response = (
                self._client.liveBroadcasts()
                .list(part="snippet", broadcastStatus="active", mine=True)
                .execute()
            )
            items = response.get("items") or []
            if not items:
                raise RuntimeError("Kein aktiver Livestream auf diesem Kanal.")
            chat_id = (items[0].get("snippet") or {}).get("liveChatId")
        else:
            response = (
                self._client.videos()
                .list(part="liveStreamingDetails", id=self.video_id)
                .execute()
            )
            items = response.get("items") or []
            if not items:
                raise RuntimeError("Video-ID nicht gefunden.")
            details = items[0].get("liveStreamingDetails") or {}
            chat_id = details.get("activeLiveChatId")
        if not chat_id:
            raise RuntimeError("Der Stream hat gerade keinen Live-Chat.")
        return str(chat_id)

    def _poll_once(self) -> float | None:
        kwargs: dict = {
            "liveChatId": self.chat_id,
            "part": "snippet,authorDetails",
            "maxResults": 200,
        }
        if self.page_token:
            kwargs["pageToken"] = self.page_token
        response = self._client.liveChatMessages().list(**kwargs).execute()
        messages, token, wait = parse_live_chat_payload(response)
        self.page_token = token
        # Der erste Aufruf liefert oft ältere Zeilen. Die wären beim Start
        # ein Schwall alter Stimmen. Wir merken uns nur den Seiten-Stempel.
        if not self.primed:
            self.primed = True
            log.info("YouTube-Chat angehängt, ältere Zeilen werden nicht gezählt.")
            return wait
        self._push(messages)
        return wait

    def _stream_metadata(self) -> list[tuple[str, str]]:
        if self.mode == "oauth":
            return [("authorization", f"Bearer {self._fresh_credentials().token}")]
        return [("x-goog-api-key", self.api_key)]

    def _wait_for_connect_slot(self) -> bool:
        """Jede neue Verbindung kostet. Mehr als eine pro min_poll_seconds gibt es nie."""
        pause = self._next_connect - time.monotonic()
        if pause > 0 and self._stop.wait(pause):
            return False
        self._next_connect = time.monotonic() + self.min_poll
        return True

    def _open_channel(self):
        from cave_dig.chat import youtube_stream

        return youtube_stream.open_channel()

    def _close_channel(self) -> None:
        if self._channel is not None:
            self._channel.close()
            self._channel = None

    def _stream_once(self) -> None:
        """Hält eine Verbindung offen, bis sie endet. Danach verbindet _run neu."""
        from cave_dig.chat import youtube_stream

        if not self._wait_for_connect_slot():
            return
        if self._channel is None:
            self._channel = self._open_channel()
        self._call = youtube_stream.open_stream(
            self._channel, self.chat_id, self.page_token, self._stream_metadata()
        )
        self._set_status("ready")
        try:
            for response in self._call:
                if response.offline_at:
                    raise RuntimeError("Der Stream ist offline.")
                self._take_stream_response(response)
        except youtube_stream.grpc.RpcError as exc:
            if youtube_stream.is_cancelled(exc) and self._stop.is_set():
                return
            if youtube_stream.is_bad_token(exc):
                self.page_token = None
                self.primed = False
            raise StreamFailed(*youtube_stream.classify_rpc_error(exc)) from exc
        finally:
            self._call = None

    def _take_stream_response(self, response) -> None:
        from cave_dig.chat import youtube_stream

        payload = youtube_stream.response_to_payload(response)
        messages, token, _wait = parse_live_chat_payload(payload)
        if token:
            self.page_token = token
        # Wie bei list: Die erste Antwort kann ältere Zeilen enthalten.
        if not self.primed:
            self.primed = True
            log.info("YouTube-Chat angehängt, ältere Zeilen werden nicht gezählt.")
            return
        self._push(messages)


def _published(value: object) -> float:
    if not isinstance(value, str) or not value:
        return 0.0
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()
