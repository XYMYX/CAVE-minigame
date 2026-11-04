"""Mehrere Chat-Quellen zusammenführen und auswählen, ohne Netz."""

from dataclasses import replace
from pathlib import Path

import pytest

from cave_dig import chat
from cave_dig.chat import _FACTORIES, create_provider
from cave_dig.chat.base import ChatMessage, ChatProvider
from cave_dig.chat.multi import MultiChatProvider
from cave_dig.chat.twitch import TwitchChatProvider
from cave_dig.chat.youtube import YouTubeChatProvider
from cave_dig.config import PROVIDER_NAMES, ConfigError, load_config, parse_providers
from cave_dig.languages import load_languages

ROOT = Path(__file__).resolve().parents[1]


class FakeProvider(ChatProvider):
    def __init__(self, *texts, status="", fail=""):
        super().__init__()
        self.texts = list(texts)
        self._status = status
        self.fail = fail
        self.calls = []

    def _step(self, name):
        self.calls.append(name)
        if self.fail == name:
            raise RuntimeError(name)

    def start(self):
        self._step("start")

    def poll(self, now):
        self._step("poll")
        items = [ChatMessage("Nora", text) for text in self.texts]
        self.texts = []
        return items

    def stop(self):
        self._step("stop")


def _texts(provider):
    return [message.text for message in provider.poll(0)]


def test_messages_of_all_sources_are_merged_once():
    multi = MultiChatProvider([FakeProvider("a", "b"), FakeProvider("c")])
    multi.start()
    assert _texts(multi) == ["a", "b", "c"]
    assert _texts(multi) == []


@pytest.mark.parametrize("step", ["poll", "stop"])
def test_failing_source_does_not_touch_the_other(step):
    bad, good = FakeProvider(fail=step), FakeProvider("a")
    multi = MultiChatProvider([bad, good])
    multi.start()
    assert _texts(multi) == ["a"]
    multi.stop()
    assert good.calls[-1] == "stop"


def test_source_that_cannot_start_is_left_out():
    bad, good = FakeProvider(fail="start"), FakeProvider("a")
    multi = MultiChatProvider([bad, good])
    multi.start()
    assert _texts(multi) == ["a"]
    multi.stop()
    assert "poll" not in bad.calls and "stop" not in bad.calls


def test_permanent_poll_failure_logs_only_once(caplog):
    multi = MultiChatProvider([FakeProvider(fail="poll")])
    multi.start()
    for _ in range(5):
        multi.poll(0)
    assert len(caplog.records) == 1


def test_status_has_one_line_per_source():
    multi = MultiChatProvider(
        [FakeProvider(status="YouTube"), FakeProvider(), FakeProvider(status="Twitch")]
    )
    assert multi.status == "YouTube\nTwitch"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("youtube", ("youtube",)),
        (" YouTube ", ("youtube",)),
        ("youtube,twitch", ("youtube", "twitch")),
        (["twitch", "youtube"], ("twitch", "youtube")),
        (["twitch", "Twitch"], ("twitch",)),
    ],
)
def test_parse_providers(value, expected):
    assert parse_providers(value) == expected


@pytest.mark.parametrize(
    ("value", "hint"),
    [
        ("kick", "kick"),
        ([], "leer"),
        (["simulator", "twitch"], "allein"),
    ],
)
def test_parse_providers_rejects(value, hint):
    with pytest.raises(ConfigError, match=hint):
        parse_providers(value)


def test_yaml_list_reaches_the_config(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("chat:\n  provider: [youtube, twitch]\n", encoding="utf-8")
    config = load_config(path)
    assert config.providers == ("youtube", "twitch")
    assert config.provider == "youtube+twitch"


def test_every_name_has_a_factory():
    assert set(_FACTORIES) == set(PROVIDER_NAMES)


def _create(providers):
    config = replace(load_config(ROOT / "config.yaml"), providers=providers)
    languages = load_languages(config.languages_file)
    return create_provider(config, languages, seed=1, demo=False)


def test_single_provider_runs_without_wrapper():
    assert isinstance(_create(("twitch",)), TwitchChatProvider)


def test_two_providers_are_wrapped():
    multi = _create(("youtube", "twitch"))
    assert isinstance(multi, MultiChatProvider)
    assert [type(item) for item in multi.providers] == [YouTubeChatProvider, TwitchChatProvider]


def test_new_provider_only_needs_a_factory(monkeypatch):
    monkeypatch.setitem(chat._FACTORIES, "test", lambda *_: FakeProvider("a"))
    assert isinstance(_create(("test",)), FakeProvider)


def test_unknown_provider_stops_with_a_clear_message():
    with pytest.raises(ConfigError, match="kick"):
        _create(("kick",))


@pytest.mark.parametrize(
    ("providers", "transport", "expected"),
    [
        (("youtube", "twitch"), "poll", 60.0),
        (("twitch",), "poll", 5.0),
        (("youtube", "twitch"), "stream", 5.0),
    ],
)
def test_steer_hold_looks_at_every_provider(providers, transport, expected):
    config = replace(
        load_config(ROOT / "config.yaml"),
        providers=providers,
        youtube_transport=transport,
        youtube_min_poll_seconds=60.0,
        hold_seconds=5.0,
    )
    assert config.steer_hold == expected
