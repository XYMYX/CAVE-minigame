"""Twitch-Zeilen zerlegen und den Empfang prüfen, ohne das Netz zu berühren."""

import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

from cave_dig.chat import twitch
from cave_dig.chat.twitch import (
    TwitchChatProvider,
    chat_message_from,
    login_lines,
    normalize_channel,
    parse_irc_line,
)
from cave_dig.config import load_config

ROOT = Path(__file__).resolve().parents[1]
CHAT_LINE = (
    "@badge-info=;display-name=Nora;tmi-sent-ts=1700000000500;user-id=123 "
    ":nora!nora@nora.tmi.twitch.tv PRIVMSG #kanal :links"
)


def _message(line):
    return chat_message_from(parse_irc_line(line))


def test_parse_splits_tags_prefix_command_and_text():
    line = parse_irc_line(CHAT_LINE + "\r\n")
    assert line.command == "PRIVMSG"
    assert line.prefix == "nora!nora@nora.tmi.twitch.tv"
    assert line.params == ("#kanal", "links")
    assert line.tags["user-id"] == "123"
    assert line.tags["badge-info"] == ""


def test_parse_keeps_colons_inside_the_text():
    assert parse_irc_line(":a!a@a PRIVMSG #k :links : rechts").params[-1] == "links : rechts"


def test_parse_lines_without_tags_or_prefix():
    ping = parse_irc_line("PING :tmi.twitch.tv")
    assert (ping.command, ping.params) == ("PING", ("tmi.twitch.tv",))
    assert parse_irc_line(":tmi.twitch.tv RECONNECT").command == "RECONNECT"


@pytest.mark.parametrize("line", ["", "   ", ":nur.prefix", "@a=b"])
def test_parse_returns_none_when_no_command_is_left(line):
    assert parse_irc_line(line) is None


def test_parse_resolves_escaped_tag_values():
    line = parse_irc_line(r"@msg=a\sb\:c\\d\n PING")
    assert line.tags["msg"] == "a b;c\\d\n"


def test_chat_line_becomes_message_with_fixed_id():
    message = _message(CHAT_LINE)
    assert message.author == "Nora"
    assert message.text == "links"
    assert message.author_id == "twitch:123"
    assert message.sent_at == 1_700_000_000.5


def test_empty_display_name_falls_back_to_login():
    assert _message("@display-name=;user-id=9 :nora!nora@n PRIVMSG #k :x").author == "nora"


def test_broken_timestamp_is_not_fatal():
    assert _message("@user-id=9;tmi-sent-ts=kaputt :n!n@n PRIVMSG #k :x").sent_at == 0.0


@pytest.mark.parametrize(
    "line",
    [
        ":n!n@n PRIVMSG #k :ohne Tags",
        "@user-id= :n!n@n PRIVMSG #k :leere Nummer",
        "@user-id=9 :n!n@n PRIVMSG #k :\x01ACTION winkt\x01",
        "@user-id=9 :tmi.twitch.tv ROOMSTATE #k",
        "@user-id=9 :n!n@n PRIVMSG #k",
    ],
)
def test_lines_that_are_no_votes_are_dropped(line):
    assert _message(line) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Mein_Kanal", "mein_kanal"),
        ("#kanal", "kanal"),
        ("https://www.twitch.tv/Kanal/videos?x=1", "kanal"),
        ("", ""),
        ("kanal\r\nQUIT", ""),
    ],
)
def test_normalize_channel(value, expected):
    assert normalize_channel(value) == expected


def test_login_needs_no_token_and_uses_a_guest_name():
    lines = login_lines("kanal")
    assert "oauth" not in " ".join(lines)
    assert any(line.startswith("NICK justinfan") for line in lines)
    assert lines[-1] == "JOIN #kanal"


class FakeConnection:
    """Spielt Server: Zeilen aus script kommen an, danach Zeitablauf oder Ende."""

    def __init__(self, script, *, then=TimeoutError):
        self.script = list(script)
        self.then = then
        self.sent = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def sendall(self, data):
        self.sent.append(data.decode("utf-8"))

    def recv(self, _size):
        if self.script:
            return self.script.pop(0)
        if self.then is TimeoutError:
            time.sleep(0.005)
            raise TimeoutError
        return self.then


def _provider(monkeypatch, connections, channel="kanal"):
    config = replace(load_config(ROOT / "config.yaml"), twitch_channel=channel)
    provider = TwitchChatProvider(config)
    waits = []

    def fake_wait(seconds):
        waits.append(seconds)
        return provider._stop.is_set()

    monkeypatch.setattr(provider._stop, "wait", fake_wait)
    pending = list(connections)

    def connect():
        if not pending:
            provider._stop.set()
            raise OSError("keine Verbindung mehr")
        item = pending.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    provider._connect = connect
    return provider, waits


JOINED = b":n!n@n.tmi.twitch.tv JOIN #kanal\r\n"


def test_messages_arrive_also_when_split_across_reads(monkeypatch):
    data = (CHAT_LINE + "\r\n").encode()
    connection = FakeConnection([JOINED, data[:20], data[20:]], then=b"")
    provider, _ = _provider(monkeypatch, [connection])
    provider._run()
    assert [message.text for message in provider.poll(0)] == ["links"]
    assert provider.poll(0) == []


def test_ping_gets_the_same_text_back(monkeypatch):
    connection = FakeConnection([b"PING :tmi.twitch.tv\r\n"], then=b"")
    provider, _ = _provider(monkeypatch, [connection])
    provider._run()
    assert "PONG :tmi.twitch.tv\r\n" in connection.sent


def test_broken_bytes_do_not_stop_the_session(monkeypatch):
    good = (CHAT_LINE + "\r\n").encode()
    connection = FakeConnection([b"\xff\xfe kaputt\r\n", good], then=b"")
    provider, _ = _provider(monkeypatch, [connection])
    provider._run()
    assert len(provider.poll(0)) == 1


def test_reconnect_command_opens_a_new_connection(monkeypatch):
    first = FakeConnection([JOINED, b":tmi.twitch.tv RECONNECT\r\n"])
    second = FakeConnection([JOINED, (CHAT_LINE + "\r\n").encode()], then=b"")
    provider, _ = _provider(monkeypatch, [first, second])
    provider._run()
    assert first.script == [] and second.script == []
    assert len(provider.poll(0)) == 1


def test_wait_grows_after_failures_and_has_a_ceiling(monkeypatch):
    errors = [OSError("weg") for _ in range(8)]
    provider, waits = _provider(monkeypatch, errors)
    provider._run()
    assert waits[:8] == [5, 10, 20, 40, 80, 160, 300, 300]


def test_confirmed_join_resets_the_wait(monkeypatch):
    joined = FakeConnection([JOINED], then=b"")
    provider, waits = _provider(monkeypatch, [OSError("a"), OSError("b"), joined, OSError("c")])
    provider._run()
    assert waits[:4] == [5, 10, 5, 10]


def test_no_join_answer_gives_up_instead_of_hanging(monkeypatch):
    monkeypatch.setattr(twitch, "JOIN_TIMEOUT", 0.02)
    provider, waits = _provider(monkeypatch, [FakeConnection([])])
    provider._run()
    assert waits[:1] == [5]


def test_silent_connection_counts_as_dead(monkeypatch):
    monkeypatch.setattr(twitch, "SILENCE_LIMIT", 0.02)
    provider, waits = _provider(monkeypatch, [FakeConnection([JOINED])])
    provider._run()
    assert waits[:1] == [5]


def test_missing_channel_waits_without_connecting(monkeypatch):
    provider, waits = _provider(monkeypatch, [], channel="")

    def stop_after_wait(seconds):
        waits.append(seconds)
        provider._stop.set()

    monkeypatch.setattr(provider._stop, "wait", stop_after_wait)
    provider._run()
    assert waits == [20]
    assert provider.status == provider._catalog.t("status.twitch_missing")


def test_status_follows_the_connection(monkeypatch):
    connection = FakeConnection([JOINED])
    provider, _ = _provider(monkeypatch, [connection])
    assert provider.status == provider._catalog.t("status.twitch_connecting")
    thread = threading.Thread(target=provider._run)
    thread.start()
    deadline = time.monotonic() + 2
    while provider.status != provider._catalog.t("status.twitch_ready"):
        assert time.monotonic() < deadline
        time.sleep(0.005)
    provider._stop.set()
    thread.join(timeout=2)
    assert not thread.is_alive()


def test_queue_keeps_only_the_newest(monkeypatch):
    provider, _ = _provider(monkeypatch, [])
    message = _message(CHAT_LINE)
    for _ in range(twitch.MAX_QUEUE + 5):
        provider._push(message)
    assert len(provider.poll(0)) == twitch.MAX_QUEUE
