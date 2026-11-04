"""YouTube-Antworten zerlegen, ohne das Netz zu berühren."""

from cave_dig.chat.youtube import (
    classify_api_error,
    normalize_video_id,
    parse_live_chat_payload,
)


def test_parse_payload_skips_broken_items():
    payload = {
        "nextPageToken": "abc",
        "pollingIntervalMillis": 8000,
        "items": [
            {
                "snippet": {
                    "displayMessage": "links",
                    "publishedAt": "2026-10-21T00:00:00Z",
                },
                "authorDetails": {"displayName": "Nora"},
            },
            {"broken": True},
            "kein dict",
        ],
    }
    messages, token, wait = parse_live_chat_payload(payload)
    assert token == "abc"
    assert wait == 8
    assert len(messages) == 1
    assert messages[0].author == "Nora"
    assert messages[0].text == "links"
    assert messages[0].sent_at > 0


def test_video_id_from_url():
    assert normalize_video_id("abcdefghijk") == "abcdefghijk"
    assert normalize_video_id("https://www.youtube.com/watch?v=abcdefghijk&t=3") == "abcdefghijk"
    assert normalize_video_id("https://youtu.be/abcdefghijk?t=1") == "abcdefghijk"
    assert normalize_video_id("https://www.youtube.com/live/abcdefghijk") == "abcdefghijk"


def test_error_classes():
    assert classify_api_error(403, "quotaExceeded") == "quota"
    assert classify_api_error(403, "dailyLimitExceeded") == "quota"
    assert classify_api_error(429, "rateLimitExceeded") == "rate"
    assert classify_api_error(403, "liveChatEnded") == "ended"
    assert classify_api_error(403, "liveChatNotFound") == "ended"
    assert classify_api_error(404, "missing") == "not_found"
    assert classify_api_error(401, "authError") == "auth"
    assert classify_api_error(500, "backendError") == "other"
