"""Sprachdateien: jeder englische Schlüssel existiert auf Deutsch."""

import re
from dataclasses import replace
from pathlib import Path

import yaml

from cave_dig.config import load_config
from cave_dig.game import Game
from cave_dig.i18n import REQUIRED_KEYS, flatten_strings, load_catalog
from cave_dig.languages import load_languages

ROOT = Path(__file__).resolve().parents[1]
_PLACEHOLDERS = re.compile(r"\{(\w+)\}")


def _flat(name: str) -> dict[str, str]:
    text = (ROOT / "locales" / name).read_text(encoding="utf-8")
    loaded = yaml.safe_load(text)
    return flatten_strings(loaded)


def test_shipped_config_defaults_to_english():
    config = load_config(ROOT / "config.yaml")
    assert config.language == "en"


def test_every_english_key_exists_in_german():
    english = _flat("en.yaml")
    german = _flat("de.yaml")
    missing = sorted(set(english) - set(german))
    assert missing == []
    for key, template in english.items():
        assert german[key].strip()
        assert _PLACEHOLDERS.findall(template) == _PLACEHOLDERS.findall(german[key])


def test_required_keys_are_in_english():
    english = _flat("en.yaml")
    missing = [key for key in REQUIRED_KEYS if key not in english]
    assert missing == []


def test_unknown_language_falls_back_to_english():
    catalog = load_catalog("zz-nope", ROOT / "locales")
    assert catalog.language == "en"
    assert catalog.t("hud.depth") == "Depth"
    assert catalog.t("hud.round", n=3) == "Round 3"


def test_event_banner_follows_language(tmp_path):
    config = load_config(ROOT / "config.yaml")
    languages = load_languages(ROOT / "languages.yaml")
    english = Game(
        replace(config, language="en", save_path=tmp_path / "en.json"),
        languages,
        seed=1,
    )
    german = Game(
        replace(config, language="de", save_path=tmp_path / "de.json"),
        languages,
        seed=1,
    )
    assert english.start_event("darkness", force=True)
    assert german.start_event("ore_vein", force=True)
    assert english.event_title() == "Darkness"
    assert german.event_title() == "Erzader"
