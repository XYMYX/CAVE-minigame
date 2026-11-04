"""config.yaml laden, Lücken füllen, Umgebungsvariablen."""

from pathlib import Path

import pytest

from cave_dig.config import ConfigError, estimate_daily_chat_units, load_config

ROOT = Path(__file__).resolve().parents[1]


def test_shipped_config_has_the_documented_values():
    config = load_config(ROOT / "config.yaml")
    assert config.title == "Cave Dig"
    assert (config.logical_width, config.logical_height) == (540, 960)
    assert (config.window_width, config.window_height) == (1080, 1920)
    assert config.fps == 60
    assert config.vote_window_seconds == 2.5
    assert config.one_vote_per_user is True
    assert config.provider == "simulator"
    assert config.blocks["gem"].points == 800
    assert config.blocks["gem"].hits == 4
    assert config.blocks["bedrock"].unbreakable is True
    assert config.blocks["charge"].explosive is True
    assert config.youtube_min_poll_seconds == 50
    assert config.block_size == 45
    assert "air" in config.blocks
    assert config.blocks["air"].solid is False


def test_missing_key_falls_back(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.delenv("YOUTUBE_VIDEO_ID", raising=False)
    monkeypatch.delenv("CAVE_DIG_PROVIDER", raising=False)
    path = tmp_path / "config.yaml"
    path.write_text("game:\n  title: Testlauf\n", encoding="utf-8")
    config = load_config(path)
    assert config.title == "Testlauf"
    assert config.vote_window_seconds == 2.5
    assert config.blocks["stone"].points == 22


def test_env_overrides_youtube(tmp_path, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    monkeypatch.setenv("YOUTUBE_VIDEO_ID", "https://www.youtube.com/watch?v=abcdefghijk&t=12")
    monkeypatch.setenv("CAVE_DIG_PROVIDER", "youtube")
    config = load_config(ROOT / "config.yaml")
    assert config.provider == "youtube"
    assert config.youtube_api_key == "test-key"
    # Die URL wird erst im YouTube-Anbieter auf die ID gekürzt. Hier bleibt der Rohwert.
    assert "abcdefghijk" in config.youtube_video_id


def test_broken_yaml_is_a_clear_error(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(":\n  - [", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)


def test_unknown_block_in_weights(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "generation:\n  bands:\n    - until_row: 10\n      fill: {nicht_da: 1}\n      veins: {stone: 1}\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="nicht_da"):
        load_config(path)


def test_daily_quota_math():
    assert estimate_daily_chat_units(50) == 8640
    assert estimate_daily_chat_units(10) == 43200
    with pytest.raises(ConfigError):
        estimate_daily_chat_units(0)
