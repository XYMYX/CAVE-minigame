"""Die offene Leitung zu YouTube: liveChatMessages.streamList über gRPC.

Bei list fragt das Spiel alle 50 Sekunden nach. Bei streamList bleibt eine
Verbindung offen, und YouTube schickt neue Nachrichten sofort. So reagiert
die Spitzhacke auf den Chat, solange die Zuschauer noch dieselbe Stelle sehen.

Diese Datei wird erst geladen, wenn der Stream gebraucht wird. Der Simulator
läuft dadurch auch dann, wenn gRPC noch nicht installiert ist.
"""

from __future__ import annotations

import grpc

from cave_dig.chat import stream_list_pb2 as pb

TARGET = "youtube.googleapis.com:443"
METHOD = "/youtube.api.v3.V3DataLiveChatMessageService/StreamList"
# Prüft alle 5 Minuten, ob die Leitung noch lebt. Eine tote Leitung meldet sich
# sonst nie. Häufiger nicht: Server trennen Verbindungen, die zu oft anklopfen.
CHANNEL_OPTIONS = (
    ("grpc.keepalive_time_ms", 300_000),
    ("grpc.keepalive_timeout_ms", 20_000),
)

_KINDS = {
    grpc.StatusCode.RESOURCE_EXHAUSTED: "rate",
    # So meldet YouTube einen beendeten oder abgeschalteten Chat.
    grpc.StatusCode.FAILED_PRECONDITION: "ended",
    grpc.StatusCode.NOT_FOUND: "not_found",
    grpc.StatusCode.PERMISSION_DENIED: "auth",
    grpc.StatusCode.UNAUTHENTICATED: "auth",
}


def open_channel() -> grpc.Channel:
    return grpc.secure_channel(TARGET, grpc.ssl_channel_credentials(), options=CHANNEL_OPTIONS)


def open_stream(
    channel: grpc.Channel,
    chat_id: str,
    page_token: str | None,
    metadata: list[tuple[str, str]],
):
    """Startet die Verbindung. Das Ergebnis liefert Antworten und lässt sich abbrechen."""
    call = channel.unary_stream(
        METHOD,
        request_serializer=pb.LiveChatMessageListRequest.SerializeToString,
        response_deserializer=pb.LiveChatMessageListResponse.FromString,
    )
    request = pb.LiveChatMessageListRequest(
        live_chat_id=chat_id,
        part=["snippet", "authorDetails"],
        page_token=page_token,
    )
    return call(request, metadata=metadata)


def response_to_payload(response: pb.LiveChatMessageListResponse) -> dict:
    """Baut die Form, die auch list liefert. So gibt es nur einen Zerleger."""
    items = []
    for item in response.items:
        # Andere Arten wie Sperr-Meldungen sind keine Stimmen.
        if item.snippet.type != pb.LiveChatMessageSnippet.TypeWrapper.TEXT_MESSAGE_EVENT:
            continue
        items.append(
            {
                "snippet": {
                    "displayMessage": item.snippet.display_message,
                    "publishedAt": item.snippet.published_at,
                },
                "authorDetails": {
                    "displayName": item.author_details.display_name,
                    "channelId": item.author_details.channel_id,
                },
            }
        )
    return {"items": items, "nextPageToken": response.next_page_token}


def classify_rpc_error(error: grpc.RpcError) -> tuple[str, str, str]:
    """Gibt Grund, Code und Text zurück. Der Text kann das Tageslimit nennen."""
    code = error.code()
    details = error.details() or ""
    lowered = details.lower()
    if "quotaexceeded" in lowered or "dailylimitexceeded" in lowered:
        return "quota", code.name, details
    # Ein falscher Schlüssel kommt als INVALID_ARGUMENT, so am echten Dienst gesehen.
    if "api key" in lowered:
        return "auth", code.name, details
    return _KINDS.get(code, "other"), code.name, details


def is_cancelled(error: grpc.RpcError) -> bool:
    return error.code() == grpc.StatusCode.CANCELLED


def is_bad_token(error: grpc.RpcError) -> bool:
    return error.code() == grpc.StatusCode.INVALID_ARGUMENT
