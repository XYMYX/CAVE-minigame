"""Die offene Leitung, gegen einen kleinen gRPC-Server auf diesem Rechner.

Kein Internet. Der Server spricht aber dasselbe Protokoll wie YouTube, darum
laufen Verbindung, Abbruch und Fehlercodes wirklich durch gRPC.
"""

import queue
import threading
import time
from concurrent import futures
from dataclasses import replace
from pathlib import Path

import grpc
import pytest

from cave_dig.chat import stream_list_pb2 as pb
from cave_dig.chat import youtube_stream
from cave_dig.chat.youtube import StreamFailed, YouTubeChatProvider
from cave_dig.config import load_config

ROOT = Path(__file__).resolve().parents[1]
TEXT = pb.LiveChatMessageSnippet.TypeWrapper.TEXT_MESSAGE_EVENT


def _response(*texts, token="seite-2", offline=""):
    items = []
    for text in texts:
        item = pb.LiveChatMessage()
        item.snippet.type = TEXT
        item.snippet.display_message = text
        item.snippet.published_at = "2026-10-21T00:00:00Z"
        item.author_details.display_name = "Nora"
        item.author_details.channel_id = "UC123"
        items.append(item)
    response = pb.LiveChatMessageListResponse(items=items, next_page_token=token)
    if offline:
        response.offline_at = offline
    return response


class FakeYouTube:
    """Jede Verbindung spielt das nächste Drehbuch ab: Antworten, dann Ende oder Fehler."""

    def __init__(self):
        self.scripts = queue.Queue()
        self.requests = []
        self.metadata = []
        self.release = threading.Event()
        handler = grpc.unary_stream_rpc_method_handler(
            self._serve,
            request_deserializer=pb.LiveChatMessageListRequest.FromString,
            response_serializer=pb.LiveChatMessageListResponse.SerializeToString,
        )
        service, method = youtube_stream.METHOD.strip("/").split("/")
        generic = grpc.method_handlers_generic_handler(service, {method: handler})
        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
        self.server.add_generic_rpc_handlers((generic,))
        self.port = self.server.add_insecure_port("127.0.0.1:0")
        self.server.start()

    def _serve(self, request, context):
        self.requests.append(request)
        self.metadata.append(dict(context.invocation_metadata()))
        for step in self.scripts.get(timeout=5):
            if isinstance(step, grpc.StatusCode):
                context.abort(step, "Testfehler")
            if step == "halten":
                while context.is_active() and not self.release.is_set():
                    time.sleep(0.01)
                return
            yield step

    def channel(self):
        return grpc.insecure_channel(f"127.0.0.1:{self.port}")


@pytest.fixture
def youtube():
    fake = FakeYouTube()
    yield fake
    fake.release.set()
    fake.server.stop(0)


def _provider(youtube, monkeypatch, **changes):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    monkeypatch.setenv("YOUTUBE_VIDEO_ID", "abcdefghijk")
    config = load_config(ROOT / "config.yaml")
    settings = {"youtube_transport": "stream", "youtube_min_poll_seconds": 0.05}
    settings.update(changes)
    provider = YouTubeChatProvider(replace(config, **settings))
    provider._open_channel = youtube.channel
    provider.chat_id = "chat-1"
    return provider


def _wait_for(check):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.01)
    return False


def _texts(provider):
    return [message.text for message in provider.poll(0)]


def test_messages_arrive_while_the_connection_stays_open(youtube, monkeypatch):
    provider = _provider(youtube, monkeypatch)
    youtube.scripts.put([_response("alt"), _response("links", "rechts"), "halten"])
    thread = threading.Thread(target=provider._stream_once)
    thread.start()
    received = []
    assert _wait_for(lambda: received.extend(_texts(provider)) or len(received) == 2)
    # Die erste Antwort kann älter sein und zählt nicht.
    assert received == ["links", "rechts"]
    assert thread.is_alive()
    assert youtube.metadata[0]["x-goog-api-key"] == "test-key"
    assert youtube.requests[0].live_chat_id == "chat-1"
    assert list(youtube.requests[0].part) == ["snippet", "authorDetails"]
    provider._stop.set()
    provider._call.cancel()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert provider.page_token == "seite-2"


def test_reconnect_resumes_at_the_last_token(youtube, monkeypatch):
    provider = _provider(youtube, monkeypatch)
    youtube.scripts.put([_response("alt", token="stelle-7")])
    youtube.scripts.put([_response("links", token="stelle-8")])
    provider._stream_once()
    provider._stream_once()
    assert youtube.requests[1].page_token == "stelle-7"
    # Mit Stempel kommt nichts Altes mehr, also zählt die erste Antwort.
    assert _texts(provider) == ["links"]


def test_new_connection_waits_for_its_slot(youtube, monkeypatch):
    provider = _provider(youtube, monkeypatch, youtube_min_poll_seconds=0.4)
    youtube.scripts.put([])
    youtube.scripts.put([])
    provider._stream_once()
    start = time.monotonic()
    provider._stream_once()
    assert time.monotonic() - start > 0.3


def test_offline_stream_is_reported(youtube, monkeypatch):
    provider = _provider(youtube, monkeypatch)
    youtube.scripts.put([_response(offline="2026-10-21T00:00:00Z")])
    with pytest.raises(RuntimeError, match="offline"):
        provider._stream_once()


@pytest.mark.parametrize(
    ("code", "kind"),
    [
        (grpc.StatusCode.RESOURCE_EXHAUSTED, "rate"),
        (grpc.StatusCode.FAILED_PRECONDITION, "ended"),
        (grpc.StatusCode.NOT_FOUND, "not_found"),
        (grpc.StatusCode.PERMISSION_DENIED, "auth"),
        (grpc.StatusCode.UNAVAILABLE, "other"),
    ],
)
def test_grpc_errors_get_a_reason(youtube, monkeypatch, code, kind):
    provider = _provider(youtube, monkeypatch)
    youtube.scripts.put([code])
    with pytest.raises(StreamFailed) as caught:
        provider._stream_once()
    assert caught.value.kind == kind


def test_rejected_token_starts_fresh(youtube, monkeypatch):
    provider = _provider(youtube, monkeypatch)
    provider.page_token = "kaputt"
    provider.primed = True
    youtube.scripts.put([grpc.StatusCode.INVALID_ARGUMENT])
    with pytest.raises(StreamFailed):
        provider._stream_once()
    assert provider.page_token is None
    assert provider.primed is False


def test_thread_survives_errors_and_stop_ends_an_open_connection(youtube, monkeypatch):
    provider = _provider(youtube, monkeypatch)
    provider._build_client = lambda: object()
    monkeypatch.setattr(provider, "_delay_for", lambda kind, backoff: 0.01)
    youtube.scripts.put([grpc.StatusCode.UNAVAILABLE])
    youtube.scripts.put([_response("alt"), _response("links"), "halten"])
    provider.start()
    assert _wait_for(lambda: provider.primed and provider._queue)
    assert _texts(provider) == ["links"]
    assert provider.status == provider._catalog.t("status.ready")
    provider.stop()
    assert not provider._thread.is_alive()


def test_other_message_types_are_not_votes():
    response = _response("links")
    banned = response.items.add()
    banned.snippet.display_message = "gesperrt"
    payload = youtube_stream.response_to_payload(response)
    assert [item["snippet"]["displayMessage"] for item in payload["items"]] == ["links"]


@pytest.mark.parametrize(
    ("code", "text", "kind"),
    [
        (grpc.StatusCode.RESOURCE_EXHAUSTED, "Request failed: quotaExceeded", "quota"),
        (grpc.StatusCode.INVALID_ARGUMENT, "API key not valid.", "auth"),
    ],
)
def test_error_text_beats_the_status_code(code, text, kind):
    class Error:
        def code(self):
            return code

        def details(self):
            return text

    assert youtube_stream.classify_rpc_error(Error())[0] == kind
